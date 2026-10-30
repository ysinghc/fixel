"""`fixel scan`: render every state, run the geometry oracles, the opacity diff and SAM, triage with Spark,
and fuse into findings (guide sections 2, 6.2-6.6).

Findings are decided by code from geometry plus pixels; Spark can only dismiss or send to review. With no key
(or --offline) the scan still runs on geometry plus the model-free opacity diff, the same fallback as a model outage.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

from . import config as cfg
from .env import load_dotenv
from .fix.agent import FixLLM, fix_finding
from .fix.worktree import Workspace, slug
from .models import Finding, Triage
from .scan import (Scanned, findings_of, models_available, scan_states, serve_static,  # noqa: F401 (re-exported)
                   triage_findings, warn_once)
from .store import ArtifactStore
from .target import TargetServer
from .verify.matrix import matrix_states, scan_baseline


async def run_scan(conf: cfg.Config, states, base_url: str | None, progress, models: bool = False
                   ) -> tuple[list[Scanned], dict[str, Triage]]:
    """Scan base_url if given, otherwise start the configured target's dev server for the duration."""
    store, par = ArtifactStore(), conf.concurrency.browser_contexts
    if base_url:
        results = await scan_states(states, base_url, store, par, progress, sam=models)
    else:
        server = TargetServer(conf.target)
        async with server as url:
            print(f"started {conf.target.name} at {url}")
            for note in server.notes:
                print(f"  note: {note}")
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


def print_event(ev: dict) -> None:
    """Stream the agent's work to the terminal."""
    t = ev["type"]
    if t == "fix.tool":
        a = ev["args"]
        detail = a.get("path") or a.get("pattern") or a.get("feature") or a.get("summary") or ""
        print(f"  -> {ev['name']} {str(detail)[:90]}")
    elif t == "fix.patch" and ev["lint"]:
        print("     BLOCKED by the linter: " + "; ".join(ev["lint"])[:160])
    elif t == "fix.verify":
        print(f"     verify {ev['item']:<17} {'ok' if ev['ok'] else 'FAILED'}")
    elif t == "fix.model_fallback":
        print(f"  !! {ev['from']} unavailable ({ev['reason']}); continuing on {ev['to']}")


def pick_finding(findings: list[Finding], selector: str | None, index: int | None) -> Finding | None:
    todo = [f for f in findings if f.status == "confirmed"]
    if index is not None:
        return todo[index - 1] if 1 <= index <= len(todo) else None
    if selector:
        hits = [f for f in todo if selector in f.key]
        return hits[0] if hits else None
    return todo[0] if todo else None


async def run_fix(conf: cfg.Config, args) -> int:
    store = ArtifactStore()
    route = (args.route or conf.routes)[0]
    states = matrix_states(route, conf.matrix)
    async with await Workspace.open(conf.target, f"fix|{route}|{args.finding or args.index or 0}") as ws:
        print(f"worktree {ws.path} ({conf.target.name} at HEAD), serving {ws.url}")
        print(f"baseline scan of {route}: {len(states)} states (model-free)")
        base = await scan_baseline(ws, states, store, conf.concurrency.browser_contexts)
        findings = findings_of(base)
        confirmed = [f for f in findings if f.status == "confirmed"]
        for i, f in enumerate(confirmed, 1):
            print(f"  {i:>2}. {f.type:<20} {' + '.join(f.locs) or f.key.split('|', 1)[1]:<48} {f.widths[0]}-{f.widths[-1]}px")
        if args.list:
            return 0
        f = pick_finding(findings, args.finding, args.index)
        if f is None:
            print("no matching confirmed finding" if confirmed else "no confirmed findings to fix")
            return 1
        if models_available() and not args.offline:
            f = f.model_copy(update={"triage": (await triage_findings(base, [f], store, conf.models.triage)).get(f.key)})
        print(f"\nfixing {f.key} with {args.model}")
        res = await fix_finding(f, ws, base, store, emit=_async(print_event), llm=FixLLM(args.model, conf.models.fixer_fallback,
                                                                                    emit=_async(print_event)))
    out = Path(args.out or f".fixel/fixes/{time.strftime('%Y%m%d-%H%M%S')}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps({"status": res.status, "model": res.model, "summary": res.summary, "turns": res.turns,
                                                  "tokens": res.tokens, "finding": f.key, "citations": res.citations,
                                                  "attempts": [a.model_dump() for a in res.attempts]}, indent=1))
    print(f"\n{res.status.upper()} on {res.model} after {res.turns} turns, {res.tokens} tokens (live calls only)")
    if res.summary:
        print(f"model: {res.summary[:300]}")
    if res.verification:
        v = res.verification
        print(f"verification: target gone {v.target_gone}, new findings {v.new_findings or 'none'}, drift {v.drifted or 'none'}, "
              f"build {v.build_ok}, lint {v.lint_ok}")
        for n in v.notes:
            print(f"  note: {n[:200]}")
    if res.status == "verified":
        patch = out / f"{slug(f.key)}.patch"
        patch.write_text(res.diff)
        print(f"\n{res.diff}\nwrote {patch}; apply it in the app directory with `git apply {patch.resolve()}`")
    else:
        print("no patch exported: only a verified fix is shown as fixed")
    return 0 if res.status == "verified" else 2


def _async(fn):
    async def inner(ev):
        fn(ev)
    return inner


def cmd_fix(args) -> int:
    conf = cfg.load(args.config) if Path(args.config).exists() else cfg.Config()
    if args.widths:
        conf.matrix.widths = args.widths
    if args.themes:
        conf.matrix.themes = args.themes
    if args.stress:
        conf.matrix.text_stress = args.stress
    return asyncio.run(run_fix(conf, args))


def cmd_serve(args) -> int:
    import uvicorn
    from .api.server import create_app
    load_dotenv()
    app = create_app(".", budget_usd=args.budget)
    print(f"fixel API and UI on http://{args.host}:{args.port}  (mode {meta_mode()}, models {'on' if models_available() else 'off'})")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_bench(args) -> int:
    from .bench import metrics, run_bench as rb
    if args.bench_cmd == "run":
        levels = rb.LEVELS if args.models == "all" else rb.LEVELS[:2] if args.models == "none" else rb.LEVELS[:3]
        bc = rb.BenchConfig(split=args.split, n_mutated=args.mutated, n_clean=args.clean, seed=args.seed, levels=levels,
                            widths=args.widths, targets=args.targets, budget_usd=args.budget, ops=args.ops, parallel=args.parallel)
        out = asyncio.run(rb.run_bench(bc))
        print(metrics.render(metrics.compute(out)))
        return 0
    run = Path(args.run) if Path(args.run).exists() else rb.ROOT / args.run
    if args.bench_cmd == "export":
        print(f"wrote {metrics.export(run, args.dest)}")
        return 0
    print(metrics.render(metrics.compute(run, labels=metrics.load_labels(run) if args.labels else None)))
    return 0


def meta_mode() -> str:
    from .meta import client
    return client.mode()


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
    fx = sub.add_parser("fix", help="fix one finding in an isolated worktree; export a patch only if the verifier passes")
    fx.add_argument("--config", default="fixel.yaml")
    fx.add_argument("--route", action="append", help="the route to fix (default: the first configured route)")
    fx.add_argument("--list", action="store_true", help="scan and list the confirmed findings, then exit")
    fx.add_argument("--index", type=int, help="fix the Nth confirmed finding (1-based, as listed)")
    fx.add_argument("--finding", help="fix the first confirmed finding whose key contains this text")
    fx.add_argument("--model", default="muse-wonder-1.0")
    fx.add_argument("--widths", type=int, nargs="+", help="restrict the verification matrix (faster, weaker)")
    fx.add_argument("--themes", nargs="+")
    fx.add_argument("--stress", nargs="+")
    fx.add_argument("--offline", action="store_true", help="skip the Spark description (the fix model still needs the API)")
    fx.add_argument("--out")
    fx.set_defaults(fn=cmd_fix)
    sv = sub.add_parser("serve", help="run the API and the demo UI")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--budget", type=float, default=10.0, help="stop starting model calls for a run once it has cost this many dollars")
    sv.set_defaults(fn=cmd_serve)
    bn = sub.add_parser("bench", help="inject known defects into corpus pages and measure detection")
    bsub = bn.add_subparsers(dest="bench_cmd", required=True)
    br = bsub.add_parser("run", help="run the benchmark on a split and print the report")
    br.add_argument("--split", choices=["dev", "test"], default="dev", help="tune on dev; report test only")
    br.add_argument("--mutated", type=int, default=60, help="mutated cases (controls included)")
    br.add_argument("--clean", type=int, default=20, help="unmutated states (false-positive rate)")
    br.add_argument("--seed", type=int, default=7)
    br.add_argument("--models", choices=["none", "sam", "all"], default="all",
                    help="none: geometry + opacity diff; sam: + SAM; all: + Spark triage (needs the API key, or replay)")
    br.add_argument("--widths", type=int, nargs="+")
    br.add_argument("--targets", nargs="+", help="only these target names")
    br.add_argument("--ops", nargs="+", help="only these mutation operators")
    br.add_argument("--budget", type=float, default=10.0)
    br.add_argument("--parallel", type=int, default=4)
    br.set_defaults(fn=cmd_bench)
    bp = bsub.add_parser("report", help="print the report for a finished run (with --labels: add human-label metrics)")
    bp.add_argument("run", help="run id or directory")
    bp.add_argument("--labels", action="store_true")
    bp.set_defaults(fn=cmd_bench)
    bx = bsub.add_parser("export", help="copy a run's metrics, report, labels and per-case summary to docs/bench/<run> for committing")
    bx.add_argument("run", help="run id or directory")
    bx.add_argument("--dest")
    bx.set_defaults(fn=cmd_bench)
    args = ap.parse_args(argv)
    load_dotenv()                                   # MODEL_API_KEY etc. from .env; real environment variables win
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
