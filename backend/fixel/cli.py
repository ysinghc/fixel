"""`fixel scan`: render every state, run the geometry oracles, write candidates (guide sections 2, 6.2, 6.3).

Geometry-only for now: pixel evidence, triage and grouping into findings come next (guide section 13).
"""
import argparse
import asyncio
import functools
import http.server
import json
import threading
import time
from collections import defaultdict
from pathlib import Path

from . import config as cfg
from .capture.browser import Browsers, capture, new_context
from .detect.oracles import run_oracles
from .models import Candidate, Capture, StateSpec
from .store import ArtifactStore


def serve_static(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *a, **k: None          # type: ignore[attr-defined]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


async def scan_states(states: list[StateSpec], base_url: str, store: ArtifactStore, parallel: int = 4,
                      progress=None) -> list[tuple[Capture, list[Candidate]]]:
    results: list[tuple[Capture, list[Candidate]]] = []
    sem = asyncio.Semaphore(parallel)
    async with Browsers() as browser:
        async def one(s: StateSpec):
            async with sem:
                ctx = await new_context(browser)
                try:
                    page, cap = await capture(ctx, base_url, s, store)
                    await page.close()
                    cands = run_oracles(cap)
                finally:
                    await ctx.close()
                results.append((cap, cands))
                if progress:
                    progress(s, len(cands))
        await asyncio.gather(*(one(s) for s in states))
    results.sort(key=lambda r: r[0].state.key)
    return results


def describe(cap: Capture, c: Candidate) -> str:
    """A readable identity for display: element tags with source location or a text snippet."""
    by_id = {e.id: e for e in cap.tiles[max(c.tile, 0)].elements}
    parts = []
    for i in c.elements:
        e = by_id.get(i)
        if e:
            parts.append(e.loc or (f"{e.tag}“{e.text[:24]}”" if e.text else e.tag))
    return " + ".join(parts) or "?"


def summarize(results) -> list[dict]:
    """Group the same candidate across states into one row with its width range (display only)."""
    groups: dict[tuple, dict] = defaultdict(lambda: {"widths": set(), "states": set()})
    for cap, cands in results:
        for c in cands:
            g = groups[(c.type, describe(cap, c))]
            g["widths"].add(cap.state.width)
            g["states"].add(cap.state.key)
    rows = [{"type": t, "where": w, "widths": sorted(g["widths"]), "states": len(g["states"])}
            for (t, w), g in groups.items()]
    return sorted(rows, key=lambda r: (r["type"], r["where"]))


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
    server = None
    base_url = args.base_url or conf.target.base_url
    if args.static:
        server, base_url = serve_static(Path(args.static))
    states = conf.states()
    out = Path(args.out or f".fixel/runs/{time.strftime('%Y%m%d-%H%M%S')}")
    out.mkdir(parents=True, exist_ok=True)
    print(f"scanning {len(states)} states at {base_url}")
    try:
        results = asyncio.run(scan_states(
            states, base_url, ArtifactStore(), conf.concurrency.browser_contexts,
            progress=lambda s, n: print(f"  {s.key:<48} {n} candidates")))
    finally:
        if server:
            server.shutdown()
    rows = summarize(results)
    (out / "candidates.json").write_text(json.dumps(
        [{"state": cap.state.model_dump(), "candidates": [c.model_dump() for c in cands]}
         for cap, cands in results], indent=1))
    (out / "summary.json").write_text(json.dumps(rows, indent=1))
    print(f"\n{len(rows)} distinct candidates (geometry only, unconfirmed):")
    for r in rows:
        w = r["widths"]
        print(f"  {r['type']:<20} {r['where']:<48} {w[0]}–{w[-1]}px  ({r['states']} states)")
    print(f"\nwrote {out}/candidates.json and summary.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fixel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="render the state matrix and run the geometry oracles")
    sc.add_argument("--config", default="fixel.yaml")
    sc.add_argument("--base-url", help="override target.base_url")
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
