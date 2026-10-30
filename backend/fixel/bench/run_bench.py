"""Benchmark runner: inject known defects into real pages and record what each detection level makes of them.

A case is a state of a corpus page with one injected defect (or a control), or a clean state. For every case the same
captured page is analysed at four cumulative levels (guide section 9.4): geometry, + opacity diff, + SAM, + Spark. Each
case is saved as JSON under .fixel/bench/<run>/cases/, so metrics and ablations are recomputed from disk and never need a
browser. Model calls go through the cache, so a rerun of the same run costs nothing.

Honesty rules: every mutated case says so (`kind: "mutated"`), the split is recorded, replay mode is recorded, and a level
whose models could not be called is stored as null, never copied from the level below.
"""
import asyncio
import json
import random
import subprocess
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path

from ..capture.browser import SNAPSHOT_JS, Browsers, capture_page, new_context, prepare
from ..detect.fuse import fuse
from ..detect.oracles import run_oracles
from ..detect.pixels import add_sam, pixel_evidence
from ..meta import client as meta
from ..models import Capture, Finding, PixelEvidence, StateSpec
from ..scan import Scanned, findings_of, models_available, triage_findings
from ..store import ArtifactStore
from ..target import TargetServer
from .. import config as cfg, cost
from . import corpus
from .mutations import BY_NAME, OPS, Mutation, inject, pick

LEVELS = ("geometry", "diff", "sam", "spark")
ROOT = Path(".fixel/bench")
FLAGGED = ("confirmed", "needs_review")


@dataclass
class BenchConfig:
    split: str = "dev"
    n_mutated: int = 60
    n_clean: int = 20
    seed: int = 7
    levels: tuple[str, ...] = LEVELS
    widths: list[int] | None = None
    targets: list[str] | None = None            # restrict to these target names
    budget_usd: float = 10.0
    parallel: int = 4
    ops: list[str] | None = None                # restrict to these operators
    out: Path | None = None


@dataclass
class Spend:
    usd: float = 0.0
    budget: float = 10.0
    calls: dict = field(default_factory=lambda: {"live": 0, "cached": 0})

    @property
    def over(self) -> bool:
        return self.usd >= self.budget

    async def emit(self, ev: dict) -> None:
        if ev.get("type") == "model.call":
            self.usd += cost.usd(ev.get("kind", ""), ev.get("model"), ev.get("usage"), ev.get("source", "live"))
            self.calls["live" if ev.get("source", "live") == "live" else "cached"] += 1


def lite(findings: list[Finding]) -> list[dict]:
    return [{"key": f.key, "type": f.type, "status": f.status, "locs": f.locs, "widths": f.widths} for f in findings]


async def analyze(page, cap: Capture, store: ArtifactStore, levels: tuple[str, ...], spend: Spend,
                  spark_model: str = "muse-spark-1.3", known: dict | None = None
                  ) -> tuple[dict[str, list[dict] | None], dict[str, str], dict]:
    """The findings of one captured state at each requested level, the reason for any level that is None, and Spark's
    verdicts by finding key. `known` holds verdicts already obtained for the unmutated state: a finding with the same key
    keeps its verdict instead of being sent to Spark again (cost control: most findings of a mutated state were already there)."""
    cands = run_oracles(cap)
    ev = [await pixel_evidence(page, cap, c) for c in cands]          # opacity diff only; SAM adds to it below
    out: dict[str, list[dict] | None] = {}
    errors: dict[str, str] = {}
    verdicts: dict = dict(known or {})
    out["geometry"] = lite(fuse([(cap, c, PixelEvidence(observable=True)) for c in cands]))
    out["diff"] = lite(fuse([(cap, c, e) for c, e in zip(cands, ev)]))
    sam_ev = ev
    if "sam" in levels or "spark" in levels:
        try:
            if spend.over:
                raise RuntimeError("budget reached")
            sam_ev = await add_sam(cap, cands, ev, store, spend.emit) if cands else ev
            out["sam"] = lite(fuse([(cap, c, e) for c, e in zip(cands, sam_ev)]))
        except Exception as e:
            out["sam"], sam_ev = None, None
            errors["sam"] = f"{type(e).__name__}: {str(e)[:100]}"
    if "spark" in levels:
        try:
            if sam_ev is None:
                raise RuntimeError("the SAM level is missing, so Spark has no evidence to triage")
            if spend.over:
                raise RuntimeError("budget reached")
            res = [Scanned(cap, cands, sam_ev)]
            fresh = [f for f in findings_of(res) if f.key not in verdicts]
            verdicts |= await triage_findings(res, fresh, store, spark_model, emit=spend.emit)
            out["spark"] = lite(findings_of(res, verdicts))
        except Exception as e:
            out["spark"] = None
            errors["spark"] = f"{type(e).__name__}: {str(e)[:100]}"
    return {k: v for k, v in out.items() if k in levels or k in ("geometry", "diff")}, errors, verdicts


def score(op: Mutation | None, target_loc: str | None, base: list[dict] | None, mutated: list[dict] | None) -> dict | None:
    """How one level did on one case, relative to what the unmutated state already showed."""
    if base is None or mutated is None:
        return None
    base_confirmed = {f["key"] for f in base if f["status"] == "confirmed"}
    base_flagged = {f["key"] for f in base if f["status"] in FLAGGED}
    new_confirmed = [f for f in mutated if f["status"] == "confirmed" and f["key"] not in base_confirmed]
    new_flagged = [f for f in mutated if f["status"] in FLAGGED and f["key"] not in base_flagged]
    r = {"new_confirmed": [f["key"] for f in new_confirmed], "any_new_confirmed": bool(new_confirmed)}
    if op is None:
        return r
    if op.control:
        # a control passes when nothing new is confirmed or sent to review: it was dismissed or not observable (or never a candidate)
        return {**r, "control_ok": not new_flagged, "new_flagged": [f["key"] for f in new_flagged]}
    hit = [f for f in new_confirmed if f["type"] in op.hits]
    # "hit" needs a finding of one of the operator's types; "involves_target" is looser: any new confirmed finding naming the target
    return {**r, "hit": bool(hit), "involves_target": any(target_loc in f["locs"] for f in new_confirmed) if target_loc else False,
            "localized": any(target_loc in f["locs"] for f in hit) if target_loc else False,
            "other_new": [f["key"] for f in new_confirmed if f["type"] not in op.hits]}


def git_state() -> dict:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "backend", "tooling"], capture_output=True, text=True).stdout.strip())
        return {"commit": sha, "dirty": dirty}
    except Exception:
        return {"commit": None, "dirty": None}


async def run_bench(bc: BenchConfig, say=print) -> Path:
    """Run the benchmark and return the run directory."""
    confs = [c for c in corpus.target_configs(bc.split) if not bc.targets or c.target.name in bc.targets]
    ops = [BY_NAME[n] for n in bc.ops] if bc.ops else list(OPS)
    levels = tuple(l for l in bc.levels if l in LEVELS)
    if any(l in levels for l in ("sam", "spark")) and not models_available():
        say("no API key and not in replay mode: running geometry + opacity diff only")
        levels = tuple(l for l in levels if l in ("geometry", "diff"))
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{bc.split}-s{bc.seed}"
    out = bc.out or ROOT / run_id
    (out / "cases").mkdir(parents=True, exist_ok=True)
    store, spend, t0 = ArtifactStore(), Spend(budget=bc.budget_usd), time.time()

    pool = [(c, s) for c in confs for s in corpus.states(c, bc.widths)]
    pool.sort(key=lambda p: (p[0].target.name, p[1].key))
    rng = random.Random(bc.seed)
    rng.shuffle(pool)
    clean_pool, mut_pool = pool[:bc.n_clean], pool[bc.n_clean:] or pool
    say(f"{bc.split} split: {len(confs)} targets, {len(pool)} states; {bc.n_mutated} mutated cases + {len(clean_pool)} clean; levels {', '.join(levels)}")

    stats = {"skipped_no_target": 0, "skipped_unstable": 0, "unfinished": 0}   # unstable: did not re-tag identically, or the injection declined
    sem = asyncio.Semaphore(bc.parallel)
    async with AsyncExitStack() as stack:
        urls = {}
        for c in confs:
            srv = TargetServer(c.target)
            urls[c.target.name] = await stack.enter_async_context(srv)
            say(f"  started {c.target.name} at {urls[c.target.name]}")
        browser = await stack.enter_async_context(Browsers())
        baselines: dict[str, asyncio.Future] = {}

        async def baseline(conf: cfg.Config, s: StateSpec):
            """Capture and analyse the unmutated state once; every case on this state shares it."""
            k = f"{conf.target.name}|{s.key}"
            if k not in baselines:
                async def go():
                    async with sem:
                        ctx = await new_context(browser)
                        try:
                            page = await prepare(ctx, urls[conf.target.name], s)
                            cap = await capture_page(page, s, store)
                            res, errs, tri = await analyze(page, cap, store, levels, spend, conf.models.triage)
                            return cap, res, errs, tri
                        finally:
                            await ctx.close()
                baselines[k] = asyncio.ensure_future(go())
            return await baselines[k]

        def write(case: dict) -> None:
            (out / "cases" / f"{case['id']}.json").write_text(json.dumps(case, indent=1))

        async def clean_case(i: int, conf: cfg.Config, s: StateSpec):
            cap, res, errs, _ = await baseline(conf, s)
            write({"id": f"clean-{i:03d}", "kind": "clean", "target": conf.target.name, "split": bc.split, "state": s.model_dump(),
                   "op": None, "control": None, "tiles": [t.png_sha for t in cap.tiles], "baseline": res, "levels": res,
                   "scores": {l: score(None, None, res[l], res[l]) for l in res}, "errors": errs})

        async def mutated_case(i: int, op: Mutation):
            rnd = random.Random(f"{bc.seed}:{i}")
            for _ in range(40):                                       # try states until the operator applies somewhere
                conf, s = rnd.choice(mut_pool)
                cap, base_res, base_errs, base_tri = await baseline(conf, s)
                chosen = pick(cap, op, rnd)
                if not chosen:
                    stats["skipped_no_target"] += 1
                    continue
                tile, el = chosen
                async with sem:
                    ctx = await new_context(browser)
                    try:
                        page = await prepare(ctx, urls[conf.target.name], s)
                        snap = await page.evaluate(SNAPSHOT_JS)
                        same = next((e for e in snap["elements"] if e["id"] == el.id), None)
                        if not same or same["loc"] != el.loc or same["tag"] != el.tag:
                            stats["skipped_unstable"] += 1           # the page did not tag the same element on a fresh render
                            continue
                        if not await inject(page, op, el.id):
                            stats["skipped_unstable"] += 1
                            continue
                        mcap = await capture_page(page, s, store)
                        res, errs, _ = await analyze(page, mcap, store, levels, spend, conf.models.triage, known=base_tri)
                    finally:
                        await ctx.close()
                write({"id": f"{conf.target.name}-{i:03d}-{op.name}", "kind": "mutated", "target": conf.target.name, "split": bc.split,
                       "state": s.model_dump(), "op": op.name, "control": op.control, "target_loc": el.loc, "target_tag": el.tag,
                       "target_tile": tile, "tiles": [t.png_sha for t in mcap.tiles], "baseline": base_res, "levels": res,
                       "scores": {l: score(op, el.loc, base_res.get(l), res.get(l)) for l in res}, "errors": {**base_errs, **errs}})
                return
            stats["unfinished"] += 1

        order = []
        for r in range((bc.n_mutated + len(ops) - 1) // len(ops)):    # stratified: every operator in turn, in a seeded order
            block = list(ops)
            random.Random(f"{bc.seed}:ops:{r}").shuffle(block)
            order += block
        jobs = [clean_case(i, c, s) for i, (c, s) in enumerate(clean_pool)]
        jobs += [mutated_case(i, op) for i, op in enumerate(order[:bc.n_mutated])]
        done = 0
        for fut in asyncio.as_completed(jobs):
            await fut
            done += 1
            if done % 10 == 0 or done == len(jobs):
                say(f"  {done}/{len(jobs)} cases   spend ${spend.usd:.3f}")

    n_cases = len(list((out / "cases").glob("*.json")))
    meta_doc = {"run": run_id, "split": bc.split, "seed": bc.seed, "levels": list(levels), "mode": meta.mode(),
                "targets": [c.target.name for c in confs], "n_states_in_pool": len(pool), "n_cases": n_cases,
                "requested": {"mutated": bc.n_mutated, "clean": len(clean_pool)}, **stats, "usd": round(spend.usd, 4),
                "model_calls": spend.calls, "seconds": round(time.time() - t0, 1), "code": git_state(),
                "ops": [o.name for o in ops], "created": time.time(), "widths": bc.widths,
                "note": "Every case with kind 'mutated' has an injected defect or control; 'clean' cases are unmodified pages."}
    (out / "meta.json").write_text(json.dumps(meta_doc, indent=1))
    say(f"wrote {n_cases} cases to {out} (${spend.usd:.3f}, {meta_doc['seconds']}s)")
    return out
