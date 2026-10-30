"""The fix agent: a tool-calling loop on Muse Wonder with Spark 1.3 as the fallback (guide section 7.3).

The model proposes edits; code decides everything that matters. Every edit goes through the linter before it stays in
the tree, and `finish` is not trusted: it runs the model-free verifier over the whole width x theme matrix, and only a
passing verification counts as fixed.

Turns are stateless (the full transcript is sent each time) so each turn is a pure function of its input: it goes
through the cached client and replays offline, which a server-held conversation (previous_response_id) could not.
"""
import hashlib
import json
from dataclasses import dataclass, field

from openai import APIConnectionError, APIStatusError

from ..meta import client as meta
from ..meta.client import call
from ..models import FixAttempt, Finding, Verification
from ..scan import Scanned
from ..store import ArtifactStore
from ..verify.matrix import verify
from .tools import TOOLS, FixContext, build_context, dispatch, summarize_result
from .worktree import Workspace

FIX_SYSTEM = """You repair one visual layout defect in a web app. You work on a copy of the code and see the page only
through the tools. Make the smallest change to CSS or className that removes the defect at every listed width.
Never change visible text, and never hide, clip, truncate or collapse content, or use !important.
Prefer intrinsic layout fixes: min-width:0 on flex children, wrapping, max-width:100%, breaking long tokens,
a breakpoint, or gap instead of negative margins.
Edit with edit_file (exact old text -> new text). A blocked edit is reverted and tells you why.
After editing, call rerender and read the result. Call finish only after a rerender shows the defect gone and no new
defects. finish runs the full width x theme check; if it fails you get the failing checks back and can keep working.
If you cannot fix it within these rules, call finish and say so."""


def sha(x) -> str:
    return hashlib.sha256((x if isinstance(x, str) else json.dumps(x, sort_keys=True)).encode()).hexdigest()


class FixLLM:
    """One model turn: transcript in, output items out. Cached by the hash of the whole transcript."""

    def __init__(self, model: str = "muse-wonder-1.0", fallback: str = "muse-spark-1.3", emit=None, timeout: float = 240):
        self.model, self.fallback, self.emit, self.timeout = model, fallback, emit, timeout
        self.tokens = 0

    async def turn(self, items: list[dict]) -> list[dict]:
        async def go():
            r = await meta.get_client().responses.create(model=self.model, instructions=FIX_SYSTEM, tools=TOOLS,
                                                         input=items, timeout=self.timeout)
            return {"output": [o.model_dump(exclude_none=True) for o in r.output],
                    "usage": r.usage.model_dump() if r.usage else None}
        key = {"model": self.model, "sys": sha(FIX_SYSTEM), "tools": sha(TOOLS), "items": sha(items), "v": 1}
        seen: dict = {}

        async def record(ev: dict) -> None:
            seen.update(ev)
            if self.emit:
                await self.emit(ev)
        try:
            out = await call("fix.turn", key, go, record)
        except (APIStatusError, APIConnectionError) as e:
            if self.model == self.fallback:
                raise
            if self.emit:                                    # Wonder is in preview: the UI names the model that produced the patch
                await self.emit({"type": "fix.model_fallback", "from": self.model, "to": self.fallback, "reason": type(e).__name__})
            self.model = self.fallback
            items[:] = [i for i in items if i.get("type") != "reasoning"]       # one model's reasoning items mean nothing to another
            return await self.turn(items)
        if seen.get("source") == "live":                       # spend only: a cached turn costs nothing
            self.tokens += (out.get("usage") or {}).get("total_tokens") or 0
        return out["output"]


@dataclass
class FixResult:
    finding_key: str
    status: str                                  # verified | failed | gave_up | budget
    model: str
    summary: str
    diff: str
    verification: Verification | None
    attempts: list[FixAttempt] = field(default_factory=list)
    turns: int = 0
    tokens: int = 0
    citations: list[str] = field(default_factory=list)


def checklist(v: Verification) -> dict:
    still = sorted(k for k, ok in v.grid.items() if not ok)
    return {"verified": v.passed, "target_defect_gone_everywhere": v.target_gone, "new_defects": v.new_findings,
            "elements_that_moved_or_resized_outside_the_fix": v.drifted, "build_ok": v.build_ok, "lint_ok": v.lint_ok,
            "states_where_defect_remains": still, "details": v.notes}


async def fix_finding(f: Finding, ws: Workspace, baseline: list[Scanned], store: ArtifactStore, emit=None,
                      llm: FixLLM | None = None, max_turns: int = 24, max_edits: int = 10, max_verifications: int = 3) -> FixResult:
    async def say(ev: dict) -> None:
        if emit:
            await emit(ev)

    llm = llm or FixLLM(emit=emit)
    text, images, ctx = await build_context(f, ws, baseline, store)
    items: list[dict] = [{"role": "user", "content": [{"type": "input_text", "text": text},
                                                      *({"type": "input_image", "image_url": u} for u in images)]}]
    attempts: list[FixAttempt] = []
    summary, verifications, turns = "", 0, 0

    async def finalize(budget: bool = False) -> FixResult:
        diff = await ws.diff()
        v = attempts[-1].verification if attempts and attempts[-1].diff == diff else None
        if v is None and diff:                                # unverified edits (budget hit, or the model just stopped)
            v = await verify(f, ws, baseline, store, emit=emit)
            attempts.append(FixAttempt(finding_key=f.key, model=llm.model, diff=diff, lint_errors=list(ctx.lint_errors),
                                       verification=v, citations=list(ctx.citations)))
        if v and v.passed:
            status = "verified"
        elif budget:
            status = "budget"
        else:
            status = "failed" if v else "gave_up"            # gave_up: the model made no edits
        res = FixResult(f.key, status, llm.model, summary, diff, v, attempts, turns, llm.tokens, list(ctx.citations))
        await say({"type": "fix.done", "status": status, "model": llm.model, "turns": turns})
        return res

    for turns in range(1, max_turns + 1):
        out = await llm.turn(items)
        items += out
        calls = [o for o in out if o.get("type") == "function_call"]
        if not calls:
            summary = " ".join(c.get("text", "") for o in out if o.get("type") == "message" for c in o.get("content", []))
            return await finalize()
        results, extra, finished = [], [], False
        for c in calls:
            args = json.loads(c.get("arguments") or "{}")
            await say({"type": "fix.tool", "name": c["name"], "args": {k: (v[:200] if isinstance(v, str) else v) for k, v in args.items()}})
            if c["name"] == "finish":
                summary = args.get("summary", "")
                diff = await ws.diff()
                if not diff:
                    results.append({"type": "function_call_output", "call_id": c["call_id"],
                                    "output": json.dumps({"verified": False, "details": ["no edits were made"]})})
                    await say({"type": "fix.tool.result", "name": "finish", "ok": False, "detail": "no edits were made"})
                    finished = True
                    continue
                await say({"type": "fix.verifying", "round": verifications + 1})
                v = await verify(f, ws, baseline, store, emit=emit)
                verifications += 1
                attempts.append(FixAttempt(finding_key=f.key, model=llm.model, diff=diff, lint_errors=list(ctx.lint_errors),
                                           verification=v, citations=list(ctx.citations)))
                results.append({"type": "function_call_output", "call_id": c["call_id"], "output": json.dumps(checklist(v))})
                await say({"type": "fix.tool.result", "name": "finish", "ok": v.passed,
                           "detail": "verified" if v.passed else "; ".join(v.notes)[:160] or "not verified"})
                finished = v.passed or verifications >= max_verifications
                continue
            result, imgs = await dispatch(c["name"], args, ctx, emit)
            await say({"type": "fix.tool.result", "name": c["name"], **summarize_result(c["name"], result)})
            results.append({"type": "function_call_output", "call_id": c["call_id"],
                            "output": result if isinstance(result, str) else json.dumps(result)})
            if imgs:
                extra.append({"role": "user", "content": [{"type": "input_text", "text": "Current render:"},
                                                          *({"type": "input_image", "image_url": u} for u in imgs)]})
        items += results + extra
        if finished:
            return await finalize()
        if ctx.edits > max_edits:
            summary = summary or "edit budget reached"
            return await finalize(budget=True)
    summary = summary or "turn budget reached"
    return await finalize(budget=True)
