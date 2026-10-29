"""Spike 4 (guide section 13): a Wonder tool loop with a real apply_patch / rerender round trip.

A throwaway git repo holds a copy of the fixture page whose 480px promo overflows phones. The model gets
read_file, apply_patch (unified diff, applied with git), rerender (the real oracles at 320/375 px) and finish.
Checks: function tools work, previous_response_id carries state, an image can follow as a user message,
and how long and how many tokens a minimal fix takes. Run: python scripts/spikes/wonder_loop.py [--model muse-wonder-1.0]
"""
import argparse
import asyncio
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from fixel.cli import findings_of, scan_states, serve_static
from fixel.detect.triage import data_url
from fixel.meta import client as meta
from fixel.models import StateSpec
from fixel.store import ArtifactStore

SYSTEM = """You repair one visual layout defect in a web page.
Make the smallest change to CSS that removes the defect at every listed width.
Never change visible text, hide or clip content, or use !important.
Prefer intrinsic layout fixes: min-width:0, wrapping, max-width:100%, a breakpoint.
After every apply_patch, call rerender and read the result. Call finish only after a rerender
shows the target defect gone. If you cannot fix it without breaking these rules, say so in finish."""


def fn(name, desc, props, req):
    return {"type": "function", "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req, "additionalProperties": False}}


TOOLS = [
    fn("read_file", "Read lines of a repository file",
       {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path", "start", "end"]),
    fn("apply_patch", "Apply a unified diff against HEAD (replaces any earlier attempt)", {"diff": {"type": "string"}}, ["diff"]),
    fn("rerender", "Re-render the failing width and its neighbours; returns oracle results", {}, []),
    fn("finish", "End the session", {"summary": {"type": "string"}}, ["summary"]),
]


def sh(*cmd, cwd, stdin=None):
    return subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True)


async def rerender(repo: Path, store) -> dict:
    server, url = serve_static(repo)
    try:
        res = await scan_states([StateSpec(route="/index.html", width=w) for w in (320, 375, 414)], url, store)
    finally:
        server.shutdown()
    found = findings_of(res)
    return {"viewport_protrusion_widths": sorted({w for f in found if f.type == "viewport_protrusion"
                                                  and f.status == "confirmed" for w in f.widths}),
            "other_findings": sorted({f.type for f in found if f.type != "viewport_protrusion"}), "png_sha": res[0].cap.tiles[0].png_sha}


async def main(model: str):
    store = ArtifactStore()
    repo = Path(tempfile.mkdtemp(prefix="wonder-spike-"))
    shutil.copy("tests/fixtures/site/index.html", repo / "index.html")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=s", "-c", "user.email=s@s", "commit", "-qm", "base"]):
        sh("git", *c, cwd=repo)
    print("before:", (await rerender(repo, store))["viewport_protrusion_widths"], "=> overflowing widths")
    client = meta.get_client()
    task = ("Defect: the .promo box in index.html is wider than the viewport, so the page scrolls sideways at "
            "320, 375 and 414 px. File: index.html. Fix it.")
    t0, tokens, trace = time.time(), 0, []
    resp = await client.responses.create(model=model, instructions=SYSTEM, tools=TOOLS,
                                         input=[{"role": "user", "content": [{"type": "input_text", "text": task}]}])
    done = False
    for turn in range(12):
        tokens += resp.usage.total_tokens if resp.usage else 0
        calls = [o for o in resp.output if o.type == "function_call"]
        if not calls:
            print("model stopped with a message:", (resp.output_text or "")[:200])
            break
        outputs, extra = [], []
        for c in calls:
            args = json.loads(c.arguments or "{}")
            trace.append(c.name)
            if c.name == "finish":
                print("finish:", args.get("summary"))
                done = True
                break
            if c.name == "read_file":
                lines = (repo / args["path"]).read_text().splitlines()
                result = "\n".join(f"{i + 1}: {l}" for i, l in enumerate(lines) if args["start"] <= i + 1 <= args["end"])
            elif c.name == "apply_patch":
                sh("git", "checkout", "--", ".", cwd=repo)
                chk = sh("git", "apply", "--check", "-", cwd=repo, stdin=args["diff"])
                if chk.returncode:
                    result = {"git_error": chk.stderr}
                else:
                    sh("git", "apply", "-", cwd=repo, stdin=args["diff"])
                    result = "applied"
                print("--- patch:\n" + args["diff"])
            else:
                r = await rerender(repo, store)
                sha = r.pop("png_sha")
                result = r
                extra = [{"role": "user", "content": [{"type": "input_text", "text": "Re-rendered 320px tile:"},
                                                      {"type": "input_image", "image_url": data_url(store.get(sha))}]}]
            outputs.append({"type": "function_call_output", "call_id": c.call_id,
                            "output": result if isinstance(result, str) else json.dumps(result)})
        if done:
            break
        resp = await client.responses.create(model=model, previous_response_id=resp.id, tools=TOOLS, input=outputs + extra)
    after = await rerender(repo, store)
    print(f"\nafter: {after['viewport_protrusion_widths']} overflowing widths; tool trace {trace}; "
          f"{time.time() - t0:.0f}s, {tokens} tokens total")
    print("git diff:\n" + sh("git", "diff", cwd=repo).stdout)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="muse-wonder-1.0")
    asyncio.run(main(ap.parse_args().model))
