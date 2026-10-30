"""The fix agent's tools and the context it starts from (guide section 7.3).

Edits are exact-match search/replace, not hand-written unified diffs: the Wonder spike needed four tries because
model-written hunk headers were wrong. The diff the linter and verifier see is always the one git derives.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..capture.browser import SNAPSHOT_JS, Browsers, new_context, prepare
from ..detect.fuse import candidate_key, text_hash
from ..detect.triage import candidate_rects, crop_and_thumb, data_url
from ..localize.cdp_styles import matched_rules
from ..meta import client as meta
from ..meta.client import call
from ..models import Capture, Candidate, Finding, StateSpec
from ..scan import Scanned, scan_states
from ..store import ArtifactStore
from ..verify.drift import line_remap, remap_key
from ..verify.matrix import confirmed_keys
from .lint import lint
from .worktree import Workspace, WorkspaceError


def fn(name, desc, props, req):
    return {"type": "function", "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req, "additionalProperties": False}}


TOOLS = [
    fn("read_file", "Read lines of a file (paths are relative to the app directory, as in the source locations)",
       {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path", "start", "end"]),
    fn("search", "Search the app's source with a regular expression (node_modules excluded)",
       {"pattern": {"type": "string"}, "glob": {"type": "string", "description": "file name glob such as *.jsx or *"}},
       ["pattern", "glob"]),
    fn("edit_file", "Replace exactly one occurrence of `old` with `new` in a file. `old` must match the file exactly "
                    "(whitespace included) and be unique; include a few surrounding lines if needed. Edits accumulate.",
       {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, ["path", "old", "new"]),
    fn("reset", "Discard all edits and return to the original code", {}, []),
    fn("rerender", "Re-render the failing width and its neighbours with the current edits; reports whether the "
                   "defect is gone, any new defects, and shows the result", {}, []),
    fn("check_css_support", "Look up current browser support for a CSS feature, with sources",
       {"feature": {"type": "string"}}, ["feature"]),
    fn("finish", "Declare the fix done. The whole width x theme matrix is then verified; if it fails you get the "
                 "failing checks back and can keep working.", {"summary": {"type": "string"}}, ["summary"]),
]


@dataclass
class FixContext:
    finding: Finding
    ws: Workspace
    baseline: list[Scanned]
    store: ArtifactStore
    cap: Capture | None = None                       # baseline capture where the target was seen
    cand: Candidate | None = None
    near_states: list[StateSpec] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    edits: int = 0
    rejected: int = 0
    lint_errors: list[str] = field(default_factory=list)      # every distinct linter message so far


def _parse_state_key(key: str) -> tuple[int, str, str]:
    _, w, theme, stress, *_ = key.split("|")
    return int(w), theme, stress


def pick_states(f: Finding, baseline: list[Scanned]) -> list[StateSpec]:
    """The failing states plus the next width on either side, for the quick rerender."""
    failing = {_parse_state_key(c.state_key)[1:] for c in f.candidates}
    widths = sorted({r.cap.state.width for r in baseline})
    fail_w = {_parse_state_key(c.state_key)[0] for c in f.candidates}
    near = set(fail_w)
    for w in fail_w:
        i = widths.index(w)
        near |= set(widths[max(0, i - 1):i + 2])
    return [r.cap.state for r in baseline if r.cap.state.width in near and (r.cap.state.theme, r.cap.state.text_stress) in failing]


def _snippets(ws: Workspace, locs: list[str], radius: int = 15) -> str:
    out, seen = [], set()
    for loc in locs:
        m = re.match(r"^(.+):(\d+):\d+$", loc)
        if not m or (m[1], m[2]) in seen:
            continue
        seen.add((m[1], m[2]))
        ln = int(m[2])
        try:
            out.append(f"--- {m[1]} around line {ln}\n{ws.read(m[1], ln - radius, ln + radius)}")
        except WorkspaceError:
            pass
    return "\n\n".join(out)


async def build_context(f: Finding, ws: Workspace, baseline: list[Scanned], store: ArtifactStore) -> tuple[str, list[str], FixContext]:
    """The task text, the images (failing crop, and a passing one when available) and the tool context."""
    ctx = FixContext(finding=f, ws=ws, baseline=baseline, store=store, near_states=pick_states(f, baseline))
    # the narrowest failing state and its candidate
    best = None
    for r in baseline:
        for c in r.candidates:
            if candidate_key(r.cap, c) == f.key and (best is None or r.cap.state.width < best[0].state.width):
                best = (r.cap, c)
    lines = [f"Defect: {f.type} (key {f.key}). Reproduces at widths {f.widths} px.",
             "Fix it with the smallest change to CSS or className. Do not change copy, and do not hide, clip or collapse anything."]
    if f.triage:
        lines += [f"What a user sees: {f.triage.what_the_user_sees}", f"Reviewer's hint: {f.triage.fix_hint}"]
    images: list[str] = []
    locs: list[str] = list(f.locs)
    css_files: set[str] = set()
    if best:
        ctx.cap, ctx.cand = best
        by_id = {e.id: e for e in ctx.cap.tiles[ctx.cand.tile].elements}
        els = [by_id[i] for i in ctx.cand.elements if i in by_id]
        for e in els:
            par = by_id.get(e.parent)
            lines.append(f"Element <{e.tag}> {e.loc or ''} text={e.text[:60]!r} rect={[round(v) for v in e.rect]} at width {ctx.cap.state.width}")
            if par and par.loc:
                locs.append(par.loc)
        # matched author CSS rules (CDP): where a width: 480px that is not in the JSX actually lives
        try:
            async with Browsers() as browser:
                page = await prepare(await new_context(browser), ws.url, ctx.cap.state)
                await page.evaluate(SNAPSHOT_JS)                 # tags elements; ids match the baseline capture
                for e in els[:2]:
                    rules = await matched_rules(page, e.id, ws.app)
                    for r in rules[:6]:
                        lines.append(f"CSS rule on <{e.tag}>: {r['selector']} {{ {r['css'][:300]} }}  [{r['file'] or 'inline'}]")
                        if r["file"] and (ws.app / r["file"]).is_file():
                            css_files.add(r["file"])
        except Exception as ex:                                # context is a help, not a requirement
            lines.append(f"(CSS rule lookup unavailable: {type(ex).__name__})")
        # the same element where the page passes: the diagnosis is often just a fixed width
        ok = [r for r in baseline if r.cap.state.theme == ctx.cap.state.theme and r.cap.state.text_stress == ctx.cap.state.text_stress
              and r.cap.state.width > ctx.cap.state.width and not any(candidate_key(r.cap, c) == f.key for c in r.candidates)]
        if ok:
            good = min(ok, key=lambda r: r.cap.state.width)
            gby = {e.id: e for e in good.cap.tiles[0].elements}
            for e in els:
                g = gby.get(e.id)
                if g:
                    lines.append(f"Same <{e.tag}> at width {good.cap.state.width} (defect absent): width {round(g.rect[2] - g.rect[0])}px "
                                 f"vs {round(e.rect[2] - e.rect[0])}px at {ctx.cap.state.width}")
        crop, thumb = crop_and_thumb(store.get(ctx.cap.tiles[ctx.cand.tile].png_sha), candidate_rects(ctx.cap, ctx.cand))
        images = [data_url(crop), data_url(thumb)]
    ws.allowed_files = {re.match(r"^(.+):\d+:\d+$", l)[1] for l in locs if re.match(r"^(.+):\d+:\d+$", l)} | css_files
    snippet = _snippets(ws, locs)
    if snippet:
        lines.append("Source:\n" + snippet)
    lines.append("You may edit only these files: " + (", ".join(sorted(ws.allowed_files)) or "(none localized: search first)"))
    return "\n".join(lines), images, ctx


# ----------------------------------------------------------------------------- dispatch
async def rerender(ctx: FixContext) -> tuple[dict, list[str]]:
    """Model-free re-scan of the failing width and its neighbours with the current edits."""
    f, ws = ctx.finding, ctx.ws
    results = await scan_states(ctx.near_states, ws.url, ctx.store, 4, sam=False)
    remap = line_remap(await ws.diff())
    target = remap_key(f.key, remap)
    before = {remap_key(k, remap) for r in ctx.baseline if r.cap.state in ctx.near_states for k in confirmed_keys([r])}
    out: dict = {"states": {}}
    new: set[str] = set()
    for r in results:
        keys = confirmed_keys([r])
        out["states"][f"{r.cap.state.width}px {r.cap.state.theme} {r.cap.state.text_stress}"] = "defect still present" if target in keys else "defect gone"
        new |= keys - before
    out["defect_gone_in_all_checked_states"] = all(v == "defect gone" for v in out["states"].values())
    out["new_defects"] = sorted(new)
    r0 = results[0]
    return out, [data_url(crop_and_thumb(ctx.store.get(r0.cap.tiles[0].png_sha), [(0, 0, r0.cap.vw, r0.cap.vh)])[1])]


async def check_css_support(ctx: FixContext, feature: str) -> dict:
    """A Spark request with web_search grounding; the sources are shown on the patch card."""
    async def go():
        r = await meta.get_client().responses.create(
            model="muse-spark-1.3", tools=[{"type": "web_search"}],
            input=[{"role": "user", "content": [{"type": "input_text", "text":
                    f"Current browser support for the CSS feature: {feature}. Two sentences: the first Chrome, Firefox and Safari "
                    "versions that support it, and any caveat."}]}])
        urls = [a.url for item in r.output if item.type == "message" for part in item.content
                for a in (getattr(part, "annotations", None) or []) if a.type == "url_citation"]
        return {"answer": r.output_text, "sources": urls, "usage": r.usage.model_dump() if r.usage else None}
    out = await call("css.support", {"feature": feature.strip().lower(), "v": 1}, go)
    ctx.citations += [u for u in out["sources"] if u not in ctx.citations]
    return {"answer": out["answer"], "sources": out["sources"]}


async def dispatch(name: str, args: dict, ctx: FixContext, emit=None) -> tuple[object, list[str]]:
    """Run one tool. Returns (result for the model, images to show it)."""
    ws = ctx.ws
    try:
        if name == "read_file":
            return ws.read(args["path"], int(args["start"]), int(args["end"])), []
        if name == "search":
            return ws.search(args["pattern"], args.get("glob") or "*") or "no matches", []
        if name == "reset":
            await ws.reset()
            return "reset to the original code", []
        if name == "rerender":
            return await rerender(ctx)
        if name == "check_css_support":
            return await check_css_support(ctx, args["feature"]), []
        if name == "edit_file":
            ctx.edits += 1
            err, before = ws.edit(args["path"], args["old"], args["new"])
            if err:
                return {"error": err}, []
            diff = await ws.diff()
            errs = lint(diff, ws.allowed_files)
            if emit:
                await emit({"type": "fix.patch", "diff": diff, "lint": errs})
            if errs:
                ws.write_back(args["path"], before)          # a blocked edit never stays in the tree
                ctx.rejected += 1
                ctx.lint_errors += [e for e in errs if e not in ctx.lint_errors]
                return {"rejected": errs, "note": "this edit was reverted; the tree is unchanged"}, []
            return {"applied": True, "diff": diff[-1500:]}, []
    except WorkspaceError as e:
        return {"error": str(e)}, []
    except (KeyError, ValueError, TypeError) as e:
        return {"error": f"bad arguments for {name}: {e}"}, []
    return {"error": f"unknown tool {name}"}, []
