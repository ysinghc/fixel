"""`fixel scan`: render every state, run the geometry oracles and the opacity diff, fuse into findings
(guide sections 2, 6.2-6.4, 6.6).

SAM evidence and Spark triage are not wired yet (they need the API key); findings are decided by geometry plus
the model-free opacity diff alone, which is also the fallback when a model is down.
"""
import argparse
import asyncio
import functools
import http.server
import json
import threading
import time
from pathlib import Path
from typing import NamedTuple

from . import config as cfg
from .capture.browser import Browsers, capture, new_context
from .detect.fuse import fuse
from .detect.oracles import run_oracles
from .detect.pixels import pixel_evidence
from .models import Candidate, Capture, Finding, PixelEvidence, StateSpec
from .store import ArtifactStore
from .target import TargetServer


def serve_static(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *a, **k: None          # type: ignore[attr-defined]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class Scanned(NamedTuple):
    cap: Capture
    candidates: list[Candidate]
    evidence: list[PixelEvidence]


async def scan_states(states: list[StateSpec], base_url: str, store: ArtifactStore, parallel: int = 4,
                      progress=None) -> list[Scanned]:
    """Capture each state, run the geometry oracles, then the opacity diff while the page is still open."""
    results: list[Scanned] = []
    sem = asyncio.Semaphore(parallel)
    async with Browsers() as browser:
        async def one(s: StateSpec):
            async with sem:
                ctx = await new_context(browser)
                try:
                    page, cap = await capture(ctx, base_url, s, store)
                    cands = run_oracles(cap)
                    evidence = [await pixel_evidence(page, cap, c) for c in cands]
                    await page.close()
                finally:
                    await ctx.close()
                results.append(Scanned(cap, cands, evidence))
                if progress:
                    progress(s, len(cands))
        await asyncio.gather(*(one(s) for s in states))
    results.sort(key=lambda r: r.cap.state.key)
    return results


def findings_of(results: list[Scanned]) -> list[Finding]:
    return fuse([(r.cap, c, e) for r in results for c, e in zip(r.candidates, r.evidence)])


async def run_scan(conf: cfg.Config, states, base_url: str | None, progress) -> list[Scanned]:
    """Scan base_url if given, otherwise start the configured target's dev server for the duration."""
    store, par = ArtifactStore(), conf.concurrency.browser_contexts
    if base_url:
        return await scan_states(states, base_url, store, par, progress)
    async with TargetServer(conf.target) as url:
        print(f"started {conf.target.name} at {url}")
        return await scan_states(states, url, store, par, progress)


def cmd_scan(args) -> int:
    conf = cfg.load(args.config) if Path(args.config).exists() else cfg.Config()
    if args.widths:
        conf.matrix.widths = args.widths
    if args.themes:
        conf.matrix.themes = args.themes
    if args.stress:
        conf.matrix.text_stress = args.stress
    if args.route:
        conf.routes = args.route
    server, base_url = None, args.base_url
    if args.static:
        server, base_url = serve_static(Path(args.static))
    states = conf.states()
    out = Path(args.out or f".fixel/runs/{time.strftime('%Y%m%d-%H%M%S')}")
    out.mkdir(parents=True, exist_ok=True)
    print(f"scanning {len(states)} states" + (f" at {base_url}" if base_url else f" of {conf.target.name}"))
    try:
        results = asyncio.run(run_scan(conf, states, base_url, lambda s, n: print(f"  {s.key:<48} {n} candidates")))
    finally:
        if server:
            server.shutdown()
    findings = findings_of(results)
    (out / "candidates.json").write_text(json.dumps(
        [{"state": r.cap.state.model_dump(), "candidates": [c.model_dump() for c in r.candidates],
          "evidence": [e.model_dump() for e in r.evidence]} for r in results], indent=1))
    (out / "findings.json").write_text(json.dumps([f.model_dump() for f in findings], indent=1))
    statuses = ("confirmed", "needs_review", "dismissed", "not_observable")
    print(f"\n{len(findings)} findings (geometry + opacity diff; SAM and Spark triage not wired yet): "
          + ", ".join(f"{sum(f.status == st for f in findings)} {st.replace('_', ' ')}" for st in statuses))
    for f in findings:
        where = " + ".join(f.locs) or f.key.split("|", 1)[1]
        print(f"  {f.status:<14} {f.type:<20} {where:<56} {f.widths[0]}–{f.widths[-1]}px")
    print(f"\nwrote {out}/findings.json and candidates.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fixel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="render the state matrix, run the oracles and the opacity diff")
    sc.add_argument("--config", default="fixel.yaml")
    sc.add_argument("--base-url", help="scan an already running app instead of starting the target")
    sc.add_argument("--static", help="serve this directory instead of using a running app")
    sc.add_argument("--route", action="append", help="override routes (repeatable)")
    sc.add_argument("--widths", type=int, nargs="+")
    sc.add_argument("--themes", nargs="+")
    sc.add_argument("--stress", nargs="+")
    sc.add_argument("--out")
    sc.set_defaults(fn=cmd_scan)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
