"""`fixel scan`: render every state, run the geometry oracles, the opacity diff and SAM, triage with Spark,
and fuse into findings (guide sections 2, 6.2-6.6).

Findings are decided by code from geometry plus pixels; Spark can only dismiss or send to review. With no key
(or --offline) the scan still runs on geometry plus the model-free opacity diff, the same fallback as a model outage.
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
from .detect.fuse import candidate_key, fuse
from .detect.oracles import run_oracles
from .detect.pixels import add_sam, pixel_evidence
from .detect.triage import triage_candidate
from .meta import client as meta
from .models import Candidate, Capture, Finding, PixelEvidence, StateSpec, Triage
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


def models_available() -> bool:
    """True when a model call can be attempted: replay serves the cache, other modes need a key."""
    if meta.mode() == "replay":
        return True
    try:
        meta.api_key()
        return True
    except KeyError:
        return False


def warn_once(msg: str, _seen: set = set()) -> None:
    if msg not in _seen:
        _seen.add(msg)
        print(f"  warning: {msg}")


async def scan_states(states: list[StateSpec], base_url: str, store: ArtifactStore, parallel: int = 4,
                      progress=None, sam: bool = False) -> list[Scanned]:
    """Capture each state, run the geometry oracles, then the opacity diff (and SAM if asked) while the page is open."""
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
                    if sam and cands:
                        try:
                            evidence = await add_sam(cap, cands, evidence, store)
                        except Exception as e:                  # model down, replay miss, no key: keep geometry + diff
                            warn_once(f"SAM evidence skipped ({type(e).__name__}: {str(e)[:80]})")
                finally:
                    await ctx.close()
                results.append(Scanned(cap, cands, evidence))
                if progress:
                    progress(s, len(cands))
        await asyncio.gather(*(one(s) for s in states))
    results.sort(key=lambda r: r.cap.state.key)
    return results


def findings_of(results: list[Scanned], triage: dict[str, Triage] | None = None) -> list[Finding]:
    return fuse([(r.cap, c, e) for r in results for c, e in zip(r.candidates, r.evidence)], triage)


async def triage_findings(results: list[Scanned], findings: list[Finding], store: ArtifactStore,
                          model: str = "muse-spark-1.3", limit: int = 60, parallel: int = 4) -> dict[str, Triage]:
    """One Spark call per confirmed finding, on its narrowest-width observable candidate (cost control)."""
    best: dict[str, tuple] = {}
    for r in results:
        for c, e in zip(r.candidates, r.evidence):
            k = candidate_key(r.cap, c)
            if e.observable and (k not in best or r.cap.state.width < best[k][0].state.width):
                best[k] = (r.cap, c, e)
    out: dict[str, Triage] = {}
    sem = asyncio.Semaphore(parallel)

    async def one(key: str):
        cap, c, e = best[key]
        async with sem:
            try:
                out[key] = await triage_candidate(cap, c, e, store, model)
            except Exception as ex:                             # that finding keeps geometry + pixels (decide(): tri=None)
                warn_once(f"triage skipped for some findings ({type(ex).__name__}: {str(ex)[:80]})")

    todo = [f.key for f in findings if f.status == "confirmed" and f.key in best][:limit]
    await asyncio.gather(*(one(k) for k in todo))
    return out


async def run_scan(conf: cfg.Config, states, base_url: str | None, progress, models: bool = False
                   ) -> tuple[list[Scanned], dict[str, Triage]]:
    """Scan base_url if given, otherwise start the configured target's dev server for the duration."""
    store, par = ArtifactStore(), conf.concurrency.browser_contexts
    if base_url:
        results = await scan_states(states, base_url, store, par, progress, sam=models)
    else:
        async with TargetServer(conf.target) as url:
            print(f"started {conf.target.name} at {url}")
            results = await scan_states(states, url, store, par, progress, sam=models)
    triage = {}
    if models:
        triage = await triage_findings(results, findings_of(results), store, conf.models.triage)
    return results, triage


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
    models = not args.offline and models_available()
    if not models:
        print("models off: geometry + opacity diff only" + ("" if args.offline else " (no API key in MODEL_API_KEY / META_MODEL_API)"))
    try:
        results, triage = asyncio.run(run_scan(conf, states, base_url,
                                               lambda s, n: print(f"  {s.key:<48} {n} candidates"), models))
    finally:
        if server:
            server.shutdown()
    findings = findings_of(results, triage)
    (out / "candidates.json").write_text(json.dumps(
        [{"state": r.cap.state.model_dump(), "candidates": [c.model_dump() for c in r.candidates],
          "evidence": [e.model_dump() for e in r.evidence]} for r in results], indent=1))
    (out / "findings.json").write_text(json.dumps([f.model_dump() for f in findings], indent=1))
    statuses = ("confirmed", "needs_review", "dismissed", "not_observable")
    print(f"\n{len(findings)} findings ({'geometry + opacity diff + SAM + Spark triage' if models else 'geometry + opacity diff'}; "
          f"{len(triage)} triaged): "
          + ", ".join(f"{sum(f.status == st for f in findings)} {st.replace('_', ' ')}" for st in statuses))
    for f in findings:
        where = " + ".join(f.locs) or f.key.split("|", 1)[1]
        print(f"  {f.status:<14} {f.type:<20} {where:<56} {f.widths[0]}–{f.widths[-1]}px")
        if f.triage:
            print(f"      spark: {f.triage.verdict} (sev {f.triage.severity}, conf {f.triage.confidence:.2f}) {f.triage.what_the_user_sees[:110]}")
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
    sc.add_argument("--offline", action="store_true", help="no model calls (SAM, Spark): geometry + opacity diff only")
    sc.add_argument("--out")
    sc.set_defaults(fn=cmd_scan)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
