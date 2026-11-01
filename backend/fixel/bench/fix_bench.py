"""Fix benchmark: break a real source file on purpose, then see whether the fix agent repairs it (guide section 9.4).

A case is one injected defect in the source of a corpus app (see source_mut.py), committed in an isolated worktree so
the agent's diff is only its own repair. The case is kept only if the model-free scan really finds the injected defect
(a new confirmed finding of the operator's type on the mutated element); otherwise it is reported as "not detected" and
never handed to the fixer. Each detected case is repaired once per arm:

  lint on   the real configuration: edits the linter blocks are reverted, and only a verified patch counts as fixed
  lint off  the same agent and case with the linter switched off, to count patches that satisfy the oracles by hiding the
            symptom (the linter is run on the result afterwards, only to classify it)

Reported per arm: verified-fix rate, revert-equivalence (the fixed pages render pixel-identical to the unmutated original
at every state of the matrix), linter blocks, patches that removed the target but failed the matrix, cost and latency.
Every case is labelled injected; a dev-split run is a tuning signal, not a headline number. Model calls go through the
cache, so a rerun costs nothing. Cases are saved as JSON under .fixel/fixbench/<run>/cases/.
"""
import asyncio
import json
import random
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import config as cfg, cost
from ..fix.agent import FixLLM, fix_finding
from ..fix.lint import lint
from ..fix.worktree import Workspace, sh
from ..meta import client as meta
from ..models import Finding
from ..scan import Scanned, findings_of, models_available
from ..store import ArtifactStore
from ..verify.matrix import matrix_states, scan_baseline
from . import corpus
from .metrics import rate
from .mutations import BY_NAME, pick
from .run_bench import git_state
from .source_mut import SOURCE_OPS, add_classes, important, tailwind_major

ROOT = Path(".fixel/fixbench")
ARMS = ("lint_on", "lint_off")


@dataclass
class FixBenchConfig:
    split: str = "dev"
    n_cases: int = 20
    seed: int = 7
    model: str = "muse-wonder-1.0"
    arms: tuple[str, ...] = ARMS
    targets: list[str] | None = None
    ops: list[str] | None = None
    widths: list[int] = field(default_factory=lambda: [320, 375, 768, 1280])   # the verification matrix (smaller than the product's)
    themes: list[str] = field(default_factory=lambda: ["light", "dark"])
    routes_per_target: int = 3
    budget_usd: float = 5.0
    max_attempts_per_case: int = 12                    # states tried before a case is abandoned as "no applicable element"
    redraw_undetected: bool = False                    # a roll keeps drawing until the scan sees the defect, and counts the draws it skipped
    out: Path | None = None


@dataclass
class Tally:
    usd: float = 0.0
    budget: float = 5.0
    listener: object = None                      # called with every event and note (the roll shows them live)

    @property
    def over(self) -> bool:
        return self.usd >= self.budget

    async def emit(self, ev: dict) -> None:
        if ev.get("type") == "model.call":
            self.usd += cost.usd(ev.get("kind", ""), ev.get("model"), ev.get("usage"), ev.get("source", "live"))
        if self.listener:
            self.listener(ev)

    def note(self, text: str, **more) -> None:
        if self.listener:
            self.listener({"type": "note", "text": text, **more})


async def git(ws: Workspace, *args: str) -> str:
    code, out = await sh("git", "-c", "user.name=fixel-bench", "-c", "user.email=bench@fixel.invalid", *args, cwd=ws.path)
    if code:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.strip()[:200]}")
    return out.strip()


def equivalence(before: list[Scanned], after: list[Scanned]) -> dict:
    """Does the page render identically to the original? Compared by the sha of every tile of every state."""
    b = {r.cap.state.key: [t.png_sha for t in r.cap.tiles] for r in before}
    a = {r.cap.state.key: [t.png_sha for t in r.cap.tiles] for r in after}
    same = [k for k in b if a.get(k) == b[k]]
    return {"identical": len(same) == len(b), "states_identical": len(same), "states": len(b), "differs": sorted(set(b) - set(same))[:8]}


async def run_arm(arm: str, f: Finding, ws: Workspace, mres: list[Scanned], orig: list[Scanned], store: ArtifactStore,
                  fc: FixBenchConfig, tally: Tally, llm_factory) -> dict:
    ws.lint_enabled = arm == "lint_on"
    await ws.reset()
    blocked_examples: list[dict] = []

    async def emit(ev: dict) -> None:
        await tally.emit(ev)
        if ev.get("type") == "fix.patch" and ev.get("lint"):
            blocked_examples.append({"lint": ev["lint"], "diff": ev["diff"][-1200:]})

    usd0, t0 = tally.usd, time.time()
    llm = llm_factory(fc.model, emit)
    tally.note(f"Fixing with {fc.model}" + (" (linter off)" if arm == "lint_off" else ""))
    res = await fix_finding(f, ws, mres, store, emit=emit, llm=llm)
    seconds = time.time() - t0
    diff = res.diff
    v = res.verification
    hiding = lint(diff, ws.allowed_files) if diff else []        # classification only: with the linter off nothing enforced it
    out = {"arm": arm, "status": res.status, "model": res.model, "turns": res.turns, "blocked": res.blocked, "seconds": round(seconds, 1),
           "usd": round(tally.usd - usd0, 4), "diff": diff, "summary": res.summary[:300], "symptom_hiding": hiding,
           "blocked_examples": blocked_examples[:3],
           "verification": None if v is None else {"target_gone": v.target_gone, "new_findings": v.new_findings, "drifted": v.drifted,
                                                  "build_ok": v.build_ok, "lint_ok": v.lint_ok, "passed": v.passed}}
    if diff:
        after = await scan_baseline(ws, [r.cap.state for r in orig], store)
        out["equivalent"] = equivalence(orig, after)
    await ws.reset()
    return out


async def run_case(i: int, conf: cfg.Config, ws: Workspace, base_by_route: dict[str, list[Scanned]], tw_major: int, fc: FixBenchConfig,
                   store: ArtifactStore, tally: Tally, ops: list[str], llm_factory, out: Path, head: str, used: set[str]) -> dict | None:
    rnd = random.Random(f"{fc.seed}:{conf.target.name}:{i}")
    op = BY_NAME[ops[i % len(ops)]]
    classes = important(SOURCE_OPS[op.name], tw_major)
    undetected = 0
    for _ in range(fc.max_attempts_per_case):
        route = rnd.choice(list(base_by_route))
        orig = base_by_route[route]
        res = rnd.choice(orig)
        picked = pick(res.cap, op, rnd)
        if not picked:
            continue
        tile, el = picked
        if f"{op.name}|{el.loc}" in used:                        # a different element each time, or the sample is one case repeated
            continue
        file = el.loc.rsplit(":", 2)[0]
        try:
            path = ws.resolve(file)
            text = path.read_text()
        except Exception:
            continue
        new, why = add_classes(text, el.loc, classes)
        if new is None:
            continue
        used.add(f"{op.name}|{el.loc}")
        tally.note(f"Injected {op.name} into <{el.tag}> at {el.loc}: added {classes}", op=op.name, loc=el.loc, classes=classes)
        path.write_text(new)
        await git(ws, "commit", "-aqm", f"fixbench: inject {op.name} at {el.loc}")
        try:
            states = [r.cap.state for r in orig]
            tally.note(f"Scanning {len(states)} screens of the broken page")
            mres = await scan_baseline(ws, states, store)
            base_keys = {f.key for f in findings_of(orig) if f.status == "confirmed"}
            found = [f for f in findings_of(mres) if f.status == "confirmed" and f.key not in base_keys
                     and f.type in op.hits and el.loc in f.locs]
            case = {"id": f"{conf.target.name}-{i:03d}-{op.name}", "kind": "injected_source", "target": conf.target.name, "split": fc.split,
                    "op": op.name, "classes": classes, "loc": el.loc, "tag": el.tag, "route": route, "state": res.cap.state.key,
                    "detected": bool(found), "other_new": sorted({f.key for f in findings_of(mres) if f.status == "confirmed"}
                                                                  - base_keys - {f.key for f in found})[:6], "arms": {}}
            tally.note("Detected: " + (found[0].key if found else "the model-free scan did not find the injected defect"), detected=bool(found))
            if not found and fc.redraw_undetected:
                undetected += 1
                continue                                          # the finally below restores the page; draw again
            case["undetected_draws_skipped"] = undetected
            if found and not tally.over:
                f = min(found, key=lambda x: len(x.widths))
                case["finding"] = f.key
                for arm in fc.arms:
                    if tally.over:
                        case["arms"][arm] = {"arm": arm, "status": "budget"}
                        continue
                    case["arms"][arm] = await run_arm(arm, f, ws, mres, orig, store, fc, tally, llm_factory)
            (out / "cases").mkdir(parents=True, exist_ok=True)
            (out / "cases" / f"{case['id']}.json").write_text(json.dumps(case, indent=1))
            return case
        finally:
            ws.lint_enabled = True
            await git(ws, "reset", "--hard", head)               # the next case starts from the pristine commit
    return None


def default_llm(model: str, emit):
    return FixLLM(model, emit=emit)


async def roll(seed: int, listener=None, split: str = "dev", model: str = "muse-wonder-1.0", budget_usd: float = 1.0,
               llm_factory=default_llm, confs: list[cfg.Config] | None = None, root: Path = ROOT / "rolls",
               ops: list[str] | None = None) -> dict:
    """One case drawn from a seed: the same seed gives the same target, operator and element, so anyone can rerun it and
    nothing is cherry-picked. Injects into the source, scans, fixes with the linter on, and returns the case (or why none)."""
    rnd = random.Random(f"roll:{seed}")
    pool = []
    for c in confs or corpus.target_configs(split):
        pkg = Path(c.target.path or ".") / "package.json"
        if pkg.exists() and tailwind_major(json.loads(pkg.read_text())):
            pool.append(c)
    if not pool:
        raise RuntimeError("no Tailwind target to inject into")
    conf = rnd.choice(sorted(pool, key=lambda c: c.target.name))
    op = rnd.choice(sorted(o for o in SOURCE_OPS if not ops or o in ops))
    major = tailwind_major(json.loads((Path(conf.target.path or ".") / "package.json").read_text()))
    fc = FixBenchConfig(split=split, n_cases=1, seed=seed, model=model, arms=("lint_on",), ops=[op], routes_per_target=2, budget_usd=budget_usd,
                        max_attempts_per_case=40, redraw_undetected=True, out=root / f"seed-{seed}")
    tally = Tally(budget=budget_usd, listener=listener)
    tally.note(f"Seed {seed}: target {conf.target.name}, operator {op}", seed=seed, target=conf.target.name, op=op)
    store = ArtifactStore()
    async with await Workspace.open(conf.target, f"roll|{seed}") as ws:
        head = await git(ws, "rev-parse", "HEAD")
        base = {}
        for route in rnd.sample(conf.routes, min(fc.routes_per_target, len(conf.routes))):
            m = cfg.Matrix(widths=fc.widths, themes=fc.themes, text_stress=["none"], height=conf.matrix.height)
            tally.note(f"Scanning {route} before the change")
            base[route] = await scan_baseline(ws, matrix_states(route, m), store)
        case = await run_case(0, conf, ws, base, major, fc, store, tally, [op], llm_factory, fc.out, head, set())
    if case is None:
        return {"seed": seed, "target": conf.target.name, "op": op, "error": "no element of this page could take that defect; roll another seed"}
    case["seed"], case["usd"] = seed, round(tally.usd, 4)
    return case


async def run_fix_bench(fc: FixBenchConfig, say=print, llm_factory=default_llm, confs: list[cfg.Config] | None = None) -> Path:
    all_confs = confs or corpus.target_configs(fc.split)
    confs = [c for c in all_confs if not fc.targets or c.target.name in fc.targets]
    if llm_factory is default_llm and not models_available():
        raise SystemExit("the fix benchmark needs the fix model: set MODEL_API_KEY, or run in replay mode on a recorded run")
    ops = [o for o in (fc.ops or list(SOURCE_OPS)) if o in SOURCE_OPS]
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{fc.split}-s{fc.seed}"
    out = fc.out or ROOT / run_id
    out.mkdir(parents=True, exist_ok=True)
    store, tally, t0 = ArtifactStore(), Tally(budget=fc.budget_usd), time.time()
    say(f"fix benchmark, {fc.split} split: {len(confs)} targets, {fc.n_cases} cases, ops {', '.join(ops)}, arms {', '.join(fc.arms)}, model {fc.model}")
    per = [fc.n_cases // len(confs) + (1 if k < fc.n_cases % len(confs) else 0) for k in range(len(confs))]
    skipped, done, failures, no_element = {}, 0, [], 0
    for conf, n in zip(confs, per):
        pkg = Path(conf.target.path or ".") / "package.json"
        major = tailwind_major(json.loads(pkg.read_text())) if pkg.exists() else None
        if major is None:
            skipped[conf.target.name] = "no Tailwind in package.json: the source operators are Tailwind classes"
            continue
        async with await Workspace.open(conf.target, f"fixbench|{fc.seed}") as ws:
            head = await git(ws, "rev-parse", "HEAD")
            say(f"  {conf.target.name}: {n} cases at {ws.url} (Tailwind {major})")
            base: dict[str, list[Scanned]] = {}
            used: set[str] = set()
            for route in conf.routes[:fc.routes_per_target]:
                m = cfg.Matrix(widths=fc.widths, themes=fc.themes, text_stress=["none"], height=conf.matrix.height)
                base[route] = await scan_baseline(ws, matrix_states(route, m), store)
            for i in range(n):
                if tally.over:
                    say("  budget reached; stopping")
                    break
                try:
                    c = await run_case(i, conf, ws, base, major, fc, store, tally, ops, llm_factory, out, head, used)
                except Exception as e:                            # one bad case must not end the run
                    failures.append({"case": f"{conf.target.name}-{i:03d}", "error": f"{type(e).__name__}: {str(e)[:160]}"})
                    await git(ws, "reset", "--hard", head)
                    continue
                done += 1
                if c is None:
                    no_element += 1
                    say(f"    case {i}: no applicable element found")
                    continue
                arms = " ".join(f"{a}={c['arms'][a]['status']}" for a in c["arms"]) or "NOT DETECTED"
                say(f"    {c['id']} {c['loc']}: {arms}   spend ${tally.usd:.3f}")
    cases = [json.loads(p.read_text()) for p in sorted((out / "cases").glob("*.json"))]
    doc = {"run": run_id, "split": fc.split, "seed": fc.seed, "model": fc.model, "arms": list(fc.arms), "mode": meta.mode(),
           "targets": [c.target.name for c in confs], "skipped_targets": skipped, "requested": fc.n_cases, "n_cases": len(cases), "no_applicable_element": no_element,
           "matrix": {"widths": fc.widths, "themes": fc.themes, "text_stress": ["none"]}, "n_failed": len(failures), "failed_cases": failures[:25],
           "usd": round(tally.usd, 4), "seconds": round(time.time() - t0, 1), "code": git_state(), "ops": ops, "created": time.time(),
           "note": "Every case is an injected source defect. A dev-split run is a tuning signal, not a headline number."}
    (out / "meta.json").write_text(json.dumps(doc, indent=1))
    say(f"wrote {len(cases)} cases to {out} (${tally.usd:.3f}, {doc['seconds']}s)")
    return out


# ----------------------------------------------------------------------------- metrics
def compute(run: Path) -> dict:
    meta_doc = json.loads((run / "meta.json").read_text())
    cases = [json.loads(p.read_text()) for p in sorted((run / "cases").glob("*.json"))]
    detected = [c for c in cases if c["detected"]]
    m: dict = {"run": meta_doc["run"], "split": meta_doc["split"], "model": meta_doc["model"], "mode": meta_doc["mode"],
               "headline": False, "note": meta_doc["note"], "n_cases": len(cases), "n_detected": len(detected),
               "requested": meta_doc.get("requested"), "no_applicable_element": meta_doc.get("no_applicable_element"),
               "detection_of_injected_source_defects": rate(len(detected), len(cases)), "usd": meta_doc["usd"], "arms": {}, "by_op": {}}
    for arm in meta_doc["arms"]:
        rs = [c["arms"][arm] for c in detected if arm in c["arms"] and c["arms"][arm]["status"] != "budget"]
        ver = [r for r in rs if r["status"] == "verified"]
        eq = [r for r in ver if r.get("equivalent", {}).get("identical")]
        hiding = [r for r in ver if r["symptom_hiding"]]
        removed_but_failed = [r for r in rs if r["status"] != "verified" and r["verification"] and r["verification"]["target_gone"]
                              and (r["verification"]["new_findings"] or r["verification"]["drifted"] or not r["verification"]["build_ok"])]
        m["arms"][arm] = {
            "n": len(rs), "verified": rate(len(ver), len(rs)), "revert_equivalent": rate(len(eq), len(ver)),
            "patches_that_pass_by_hiding_the_symptom": rate(len(hiding), len(ver)) if arm == "lint_off" else None,
            "linter_blocks": sum(r["blocked"] for r in rs), "cases_with_a_block": sum(1 for r in rs if r["blocked"]),
            "removed_target_but_failed_the_matrix": len(removed_but_failed),
            "gave_up_or_failed": sum(1 for r in rs if r["status"] in ("gave_up", "failed")),
            # later arms replay the first arm's cached turns until the two diverge, so their cost is not a measurement
            "usd_per_fix_attempt": round(sum(r["usd"] for r in rs) / len(rs), 4) if rs and arm == meta_doc["arms"][0] else None,
            "seconds_per_fix_attempt": round(sum(r["seconds"] for r in rs) / len(rs), 1) if rs else None,
            "turns_mean": round(sum(r["turns"] for r in rs) / len(rs), 1) if rs else None}
    for op in sorted({c["op"] for c in cases}):
        cs = [c for c in cases if c["op"] == op]
        row = {"cases": len(cs), "detected": sum(c["detected"] for c in cs)}
        for arm in meta_doc["arms"]:
            rs = [c["arms"][arm] for c in cs if c["detected"] and arm in c["arms"]]
            row[arm] = f"{sum(r['status'] == 'verified' for r in rs)}/{len(rs)}"
        m["by_op"][op] = row
    on, off = m["arms"].get("lint_on"), m["arms"].get("lint_off")
    if on and off:
        m["linter_effect"] = {"verified_on": on["verified"], "verified_off": off["verified"],
                              "hiding_patches_that_pass_the_oracles_with_the_linter_off": off["patches_that_pass_by_hiding_the_symptom"]}
    m["recorded_blocked_attempt"] = next(({"case": c["id"], **r["blocked_examples"][0]} for c in detected for r in c["arms"].values()
                                          if r.get("blocked_examples")), None)
    return m


def pct(r: dict | None) -> str:
    return "n/a" if not r else f"{r['k']}/{r['n']} = {r['p'] * 100:.0f}%  (95% CI {r['lo'] * 100:.0f}-{r['hi'] * 100:.0f}%)"


def render(m: dict) -> str:
    L = [f"Fix benchmark {m['run']}  split={m['split']}  model={m['model']}  mode={m['mode']}",
         "NOT A HEADLINE: " + m["note"] if not m["headline"] else "", "",
         f"Injected source defects: {m['n_cases']} cases ({m['requested']} requested; {m['no_applicable_element']} draws found no element the operator could edit), "
         f"{m['n_detected']} found by the model-free scan "
         f"({pct(m['detection_of_injected_source_defects'])}); only those were handed to the fixer. Spend ${m['usd']:.2f}."]
    for arm, a in m["arms"].items():
        L += ["", f"[{arm}]  {a['n']} fix attempts",
              f"  verified-fix rate        {pct(a['verified'])}",
              f"  revert-equivalence       {pct(a['revert_equivalent'])} of verified fixes render pixel-identical to the original",
              f"  linter blocks            {a['linter_blocks']} edits blocked in {a['cases_with_a_block']} cases",
              f"  removed target, failed   {a['removed_target_but_failed_the_matrix']} patches removed the target but failed the matrix (regressions caught)",
              f"  failed / gave up         {a['gave_up_or_failed']}",
              f"  cost / latency           {'$' + str(a['usd_per_fix_attempt']) if a['usd_per_fix_attempt'] is not None else 'cost not measured (replays the first arm\'s cache)'}"
              f" and {a['seconds_per_fix_attempt']}s per attempt, {a['turns_mean']} turns"]
        if a["patches_that_pass_by_hiding_the_symptom"]:
            L.append(f"  PASSED BY HIDING         {pct(a['patches_that_pass_by_hiding_the_symptom'])} of its verified patches would be blocked by the linter")
    L += ["", "By operator (detected/cases, then verified/attempted per arm):"]
    for op, r in m["by_op"].items():
        L.append(f"  {op:<16} {r['detected']}/{r['cases']}  " + "  ".join(f"{a}={r[a]}" for a in m["arms"]))
    b = m.get("recorded_blocked_attempt")
    if b:
        L += ["", f"A recorded blocked attempt ({b['case']}): {'; '.join(b['lint'])[:200]}"]
    return "\n".join(l for l in L if l is not None)
