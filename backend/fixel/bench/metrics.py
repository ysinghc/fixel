"""Metrics and ablations, recomputed from a run's case files (guide section 9.4). No browser, no model calls.

Ground truth, in order of trust (guide section 9.3):
  1. human labels: state-level precision/recall and the clean-page false-positive rate. These are the headline numbers,
     and only a *test-split* run with labels is called a headline.
  2. construction: the banner operators and the three controls have known answers without running any geometry.
  3. agreement with the injected defect (geometric truth): used for regression and tuning, never quoted as accuracy.
Proportions carry Wilson 95% intervals; with a few hundred cases they are wide, and the report says so.
"""
import json
import math
import time
from collections import defaultdict
from pathlib import Path

LABELS = ("visible_defect", "no_visible_defect", "unsure")
LEVEL_NAMES = {"geometry": "geometry", "diff": "+ opacity diff", "sam": "+ SAM 3.1", "spark": "+ Spark 1.3 triage"}
CONTROL_EXPECTED = {"badge_overlap": "dismissed", "open_dropdown": "dismissed", "invisible_overlap": "not_observable"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def rate(k: int, n: int) -> dict | None:
    if n == 0:
        return None
    lo, hi = wilson(k, n)
    return {"k": int(k), "n": n, "p": round(k / n, 4), "lo": round(lo, 4), "hi": round(hi, 4)}


def load_cases(run: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((Path(run) / "cases").glob("*.json"))]


def load_meta(run: Path) -> dict:
    p = Path(run) / "meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


def labels_path(run: Path) -> Path:
    return Path(run) / "labels.json"


def load_labels(run: Path) -> dict[str, str]:
    p = labels_path(run)
    return {k: v["label"] for k, v in json.loads(p.read_text()).items()} if p.exists() else {}


def put_label(run: Path, case_id: str, label: str, who: str = "human") -> None:
    if label not in LABELS:
        raise ValueError(f"label must be one of {LABELS}")
    p = labels_path(run)
    cur = json.loads(p.read_text()) if p.exists() else {}
    cur[case_id] = {"label": label, "ts": time.time(), "by": who}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1))
    tmp.replace(p)


def flagged(case: dict, level: str) -> bool | None:
    fs = case["levels"].get(level)
    return None if fs is None else any(f["status"] == "confirmed" for f in fs)


def compute(run: Path, labels: dict[str, str] | None = None) -> dict:
    run = Path(run)
    cases, meta = load_cases(run), load_meta(run)
    levels = [l for l in ("geometry", "diff", "sam", "spark") if any(c["levels"].get(l) is not None for c in cases)]
    if labels is None:
        labels = load_labels(run)
    mutated = [c for c in cases if c["kind"] == "mutated"]
    clean = [c for c in cases if c["kind"] == "clean"]
    out: dict = {"run": run.name, "meta": meta, "levels": levels, "n_cases": len(cases), "n_mutated": len(mutated), "n_clean": len(clean)}

    # ---------------------------------------------------------------- 2. by construction
    cons: dict = {}
    for lv in levels:
        rows = {}
        for op in ("opaque_banner", "ghost_banner"):
            sc = [s for s in (c["scores"].get(lv) for c in mutated if c["op"] == op) if s]
            rows[op] = rate(sum(s["hit"] for s in sc), len(sc))
        for op in CONTROL_EXPECTED:
            sc = [s for s in (c["scores"].get(lv) for c in mutated if c["op"] == op) if s]
            rows[op] = rate(sum(s["control_ok"] for s in sc), len(sc))
        ctl = [s for s in (c["scores"].get(lv) for c in mutated if c["control"]) if s]
        rows["controls"] = rate(sum(s["control_ok"] for s in ctl), len(ctl))
        cons[lv] = rows
    out["construction"] = cons

    # ---------------------------------------------------------------- 3. agreement with the injected defect (not accuracy)
    agree: dict = {}
    loc: dict = {}
    for lv in levels:
        per_op: dict = defaultdict(lambda: [0, 0])
        any_k = any_n = 0
        lk = ln = 0
        for c in mutated:
            s = c["scores"].get(lv)
            if not s or c["control"]:
                continue
            per_op[c["op"]][1] += 1
            per_op[c["op"]][0] += s["hit"]
            any_n += 1
            any_k += s.get("involves_target", False)
            if s["hit"]:
                ln += 1
                lk += s["localized"]
        agree[lv] = {op: rate(k, n) for op, (k, n) in sorted(per_op.items())}
        agree[lv]["_all"] = rate(sum(k for k, _ in per_op.values()), sum(n for _, n in per_op.values()))
        agree[lv]["_involves_target"] = rate(any_k, any_n)
        loc[lv] = rate(lk, ln)
    out["injected_agreement"] = agree
    out["localization"] = loc

    # ---------------------------------------------------------------- 1. human labels
    ids = {c["id"] for c in cases}
    lab = {cid: l for cid, l in labels.items() if cid in ids}
    out["labels"] = {"n": len(lab), **{k: sum(v == k for v in lab.values()) for k in LABELS}}
    human = None
    if lab:
        human = {}
        for lv in levels:
            tp = fp = fn = tn = 0
            per_type: dict = defaultdict(lambda: [0, 0])    # type -> [states a human called visible, states where Fixel confirmed it]
            inj: dict = defaultdict(lambda: [0, 0])
            cfp = [0, 0]
            for c in cases:
                l = lab.get(c["id"])
                f = flagged(c, lv)
                if l not in ("visible_defect", "no_visible_defect") or f is None:
                    continue
                pos = l == "visible_defect"
                tp += pos and f
                fp += (not pos) and f
                fn += pos and not f
                tn += (not pos) and not f
                for t in {x["type"] for x in c["levels"][lv] if x["status"] == "confirmed"}:
                    per_type[t][1] += 1
                    per_type[t][0] += pos
                if c["kind"] == "clean" and not pos:
                    cfp[1] += 1
                    cfp[0] += f
                if c["kind"] == "mutated" and not c["control"] and pos:
                    inj[c["op"]][1] += 1
                    inj[c["op"]][0] += bool(c["scores"][lv] and c["scores"][lv]["any_new_confirmed"])
            human[lv] = {"confusion": {"tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn)},
                         "precision": rate(tp, tp + fp), "recall": rate(tp, tp + fn),
                         "clean_false_positive_rate": rate(*cfp),
                         "precision_by_type": {t: rate(k, n) for t, (k, n) in sorted(per_type.items())},
                         "injected_recall_by_op": {op: rate(k, n) for op, (k, n) in sorted(inj.items())}}
    out["human"] = human

    # ---------------------------------------------------------------- headline status, and the caveats that go with it
    tested = meta.get("split") == "test"
    out["headline"] = bool(human) and tested
    out["caveats"] = [
        "All non-clean cases carry an injected defect or control (kind 'mutated'); they are not real bugs found in the wild.",
        *(["REPLAY MODE: model answers came from the cache."] if meta.get("mode") == "replay" else []),
        *([] if tested else [f"Split '{meta.get('split')}' is the development split: numbers here tune thresholds and are not results."]),
        *([] if human else ["No human labels yet: the only truth available is by construction and agreement with the injection, "
                            "which is not detection accuracy."]),
        *(["The code had uncommitted changes in backend/ or tooling/ when this ran."] if (meta.get("code") or {}).get("dirty") else []),
    ]
    if meta.get("skipped_no_target") or meta.get("unfinished"):
        out["caveats"].append(f"{meta.get('unfinished', 0)} requested cases could not be placed (an operator found no target); "
                              f"{meta.get('skipped_no_target', 0)} placement attempts were skipped.")
    if meta.get("n_failed"):
        out["caveats"].append(f"{meta['n_failed']} cases crashed (for example: {(meta.get('failed_cases') or [{}])[0].get('error', '?')}) and are missing from every number here.")
    missing = {l: sum(c["levels"].get(l) is None for c in cases) for l in ("sam", "spark") if l in meta.get("levels", [])}
    if any(missing.values()):
        out["caveats"].append("Cases whose model level failed are excluded from that level: " + ", ".join(f"{l} {n}" for l, n in missing.items() if n))
    usd = meta.get("usd")
    out["cost"] = {"usd": usd, "model_calls": meta.get("model_calls"), "seconds": meta.get("seconds"),
                   "usd_per_case": round(usd / max(len(cases), 1), 4) if usd is not None else None,
                   "seconds_per_case": round(meta["seconds"] / max(len(cases), 1), 2) if meta.get("seconds") else None}
    return out


def pct(r: dict | None) -> str:
    return "n/a" if not r else f"{r['p'] * 100:5.1f}% ({r['k']}/{r['n']}, 95% CI {r['lo'] * 100:.0f}-{r['hi'] * 100:.0f}%)"


def short(r: dict | None) -> str:
    return "n/a" if not r else f"{r['k']}/{r['n']}"


def render(m: dict) -> str:
    meta = m["meta"]
    head = "HEADLINE RESULT (test split, human labels)" if m["headline"] else "NOT A HEADLINE RESULT"
    lines = [f"\n=== Benchmark {m['run']} — {head} ===",
             f"split {meta.get('split')} · seed {meta.get('seed')} · mode {meta.get('mode')} · targets {', '.join(meta.get('targets', []))} · "
             f"{m['n_mutated']} mutated (injected) + {m['n_clean']} clean cases · code {(meta.get('code') or {}).get('commit')}"]
    lines += [f"  ! {c}" for c in m["caveats"]]
    lines.append("\nBy construction (known answers, no geometry involved)")
    for lv in m["levels"]:
        c = m["construction"][lv]
        lines.append(f"  {LEVEL_NAMES[lv]:<22} opaque banner {pct(c['opaque_banner'])}")
        lines.append(f"  {'':<22} ghost banner  {pct(c['ghost_banner'])}   (hit testing is blind to it: a known gap)")
        lines.append(f"  {'':<22} controls pass {pct(c['controls'])}  [badge {short(c['badge_overlap'])}, dropdown {short(c['open_dropdown'])}, invisible {short(c['invisible_overlap'])}]")
    lines.append("\nAgreement with the injected defect (regression signal, not detection accuracy)")
    for lv in m["levels"]:
        a = m["injected_agreement"][lv]
        lines.append(f"  {LEVEL_NAMES[lv]:<22} type-matched {pct(a.get('_all'))}   localized when hit {pct(m['localization'][lv])}")
        lines.append(f"  {'':<22} looser: any new finding naming the target {pct(a.get('_involves_target'))}")
        lines.append("      " + "  ".join(f"{op} {short(a[op])}" for op in a if not op.startswith("_")))
    if m["human"]:
        lb = m["labels"]
        lines.append(f"\nAgainst human labels ({lb['n']} labelled: {lb['visible_defect']} visible, {lb['no_visible_defect']} none, {lb['unsure']} unsure; unsure excluded)")
        for lv in m["levels"]:
            h = m["human"][lv]
            lines.append(f"  {LEVEL_NAMES[lv]:<22} precision {pct(h['precision'])}")
            lines.append(f"  {'':<22} recall    {pct(h['recall'])}")
            lines.append(f"  {'':<22} clean-page false positives {pct(h['clean_false_positive_rate'])}")
    else:
        lines.append("\nAgainst human labels: none yet (label cases in the UI: Label tab).")
    c = m["cost"]
    lines.append(f"\nCost: ${c['usd']} over {m['n_cases']} cases ({c['usd_per_case']} per case, {c['seconds_per_case']}s per case); model calls {c['model_calls']}")
    return "\n".join(lines)


def export(run: Path, dest: Path | None = None) -> Path:
    """Copy what is worth committing out of the gitignored .fixel/: metrics, report, labels, queue and a per-case summary.
    Screenshots and raw case files stay local (they are large and re-creatable from the seed)."""
    import csv
    run = Path(run)
    dest = Path(dest) if dest else Path("docs/bench") / run.name
    dest.mkdir(parents=True, exist_ok=True)
    m = compute(run)
    (dest / "metrics.json").write_text(json.dumps(m, indent=1))
    (dest / "report.txt").write_text(render(m) + "\n")
    for name in ("meta.json", "labels.json", "label_queue.json"):
        if (run / name).exists():
            (dest / name).write_text((run / name).read_text())
    labels = load_labels(run)
    with (dest / "cases.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        levels = m["levels"]
        w.writerow(["id", "kind", "operator", "target", "route", "width", "theme", "text", "human_label",
                    *[f"{lv}_confirmed_findings" for lv in levels], *[f"{lv}_hit" for lv in levels]])
        for c in load_cases(run):
            s = c["state"]
            w.writerow([c["id"], c["kind"], c["op"] or "", c["target"], s["route"], s["width"], s["theme"], s["text_stress"],
                        labels.get(c["id"], ""),
                        *[("" if c["levels"].get(lv) is None else sum(f["status"] == "confirmed" for f in c["levels"][lv])) for lv in levels],
                        *[("" if not c["scores"].get(lv) else c["scores"][lv].get("hit", c["scores"][lv].get("control_ok", ""))) for lv in levels]])
    return dest
