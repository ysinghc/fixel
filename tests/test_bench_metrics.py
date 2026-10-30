"""Scoring, metrics, the labelling queue and the benchmark API, on hand-built case files (no browser, no models)."""
import json
from pathlib import Path

import pytest

from fixel.api.server import create_app
from fixel.bench import labelling, metrics
from fixel.bench.mutations import BY_NAME
from fixel.bench.run_bench import score
from helpers import Live


def f(key, type_, status="confirmed", locs=()):
    return {"key": key, "type": type_, "status": status, "locs": list(locs), "widths": [320]}


# ----------------------------------------------------------------------------- score(): what counts as a hit
def test_a_hit_needs_a_new_finding_of_the_operators_type_and_localization_needs_the_target():
    op = BY_NAME["fixed_width"]
    base = [f("viewport_protrusion|a.jsx:1", "viewport_protrusion", locs=["a.jsx:1"])]
    mutated = base + [f("viewport_protrusion|b.jsx:9", "viewport_protrusion", locs=["b.jsx:9"])]
    s = score(op, "b.jsx:9", base, mutated)
    assert s["hit"] and s["localized"] and s["involves_target"]
    s = score(op, "c.jsx:1", base, mutated)                          # found something new, but not at the mutated element
    assert s["hit"] and not s["localized"] and not s["involves_target"]


def test_a_defect_that_was_already_there_is_not_credited_to_the_mutation():
    op = BY_NAME["fixed_width"]
    base = [f("viewport_protrusion|a.jsx:1", "viewport_protrusion", locs=["a.jsx:1"])]
    assert not score(op, "a.jsx:1", base, base)["hit"]


def test_a_new_finding_of_another_type_is_not_a_type_match_but_is_reported():
    op = BY_NAME["clamp_height"]                                     # hits: clipped_text only
    s = score(op, "a.jsx:1", [], [f("collision|a.jsx:1|a.jsx:2", "collision", locs=["a.jsx:1"])])
    assert not s["hit"] and s["involves_target"] and s["other_new"]


def test_controls_pass_only_when_nothing_new_is_confirmed_or_sent_to_review():
    op = BY_NAME["badge_overlap"]
    assert score(op, "a.jsx:1", [], [f("k", "collision", status="dismissed")])["control_ok"]
    assert score(op, "a.jsx:1", [], [f("k", "collision", status="not_observable")])["control_ok"]
    assert score(op, "a.jsx:1", [], [])["control_ok"]
    assert not score(op, "a.jsx:1", [], [f("k", "collision", status="confirmed")])["control_ok"]
    assert not score(op, "a.jsx:1", [], [f("k", "collision", status="needs_review")])["control_ok"]


def test_a_missing_level_scores_none_and_is_never_copied_from_the_level_below():
    assert score(BY_NAME["fixed_width"], "a", [], None) is None


# ----------------------------------------------------------------------------- a run on disk
def case(cid, kind, level_findings, op=None, base=None, loc="a.jsx:1"):
    o = BY_NAME[op] if op else None
    base = base or {lv: [] for lv in level_findings}
    return {"id": cid, "kind": kind, "target": "app", "split": "test",
            "state": {"route": "/", "width": 320, "height": 800, "theme": "light", "text_stress": "none", "replay": []},
            "op": op, "control": o.control if o else None, "target_loc": loc if o else None, "tiles": ["0" * 64],
            "baseline": base, "levels": level_findings,
            "scores": {lv: score(o, loc if o else None, base[lv], level_findings[lv]) for lv in level_findings}, "errors": {}}


def write_run(root: Path, split="test", name="r1"):
    run = root / name
    (run / "cases").mkdir(parents=True)
    hit = {"geometry": [f("viewport_protrusion|a.jsx:1", "viewport_protrusion", locs=["a.jsx:1"])]}
    hit["diff"] = hit["geometry"]
    none = {"geometry": [], "diff": []}
    fp = {"geometry": [f("collision|x|y", "collision")], "diff": []}      # geometry alone raises it; the pixels dismiss it
    cases = [
        case("m1", "mutated", hit, "fixed_width"), case("m2", "mutated", none, "fixed_width"),
        case("m3", "mutated", hit, "fixed_width"), case("c1", "mutated", fp, "badge_overlap"),
        case("k1", "clean", none), case("k2", "clean", fp), case("k3", "clean", none),
    ]
    for c in cases:
        (run / "cases" / f"{c['id']}.json").write_text(json.dumps(c))
    (run / "meta.json").write_text(json.dumps({"run": name, "split": split, "seed": 1, "levels": ["geometry", "diff"], "mode": "record",
                                               "usd": 0.0, "seconds": 7.0, "model_calls": {"live": 0, "cached": 0}, "created": 1.0,
                                               "n_cases": len(cases), "targets": ["app"], "code": {"commit": "abc", "dirty": False}}))
    return run


def test_without_labels_nothing_is_called_accuracy_or_headline(tmp_path):
    m = metrics.compute(write_run(tmp_path))
    assert m["human"] is None and m["headline"] is False
    assert any("injected" in c for c in m["caveats"]) and any("No human labels" in c for c in m["caveats"])
    assert m["injected_agreement"]["geometry"]["fixed_width"]["k"] == 2           # 2 of 3 fixed_width cases hit
    assert m["construction"]["geometry"]["badge_overlap"]["k"] == 0               # geometry alone cannot dismiss a control
    assert m["construction"]["diff"]["badge_overlap"]["k"] == 1                   # the pixels do


def test_human_label_metrics_are_computed_per_level_and_unsure_is_excluded(tmp_path):
    run = write_run(tmp_path)
    for cid, lab in {"m1": "visible_defect", "m2": "visible_defect", "m3": "unsure", "c1": "no_visible_defect",
                     "k1": "no_visible_defect", "k2": "no_visible_defect"}.items():
        metrics.put_label(run, cid, lab)
    m = metrics.compute(run)
    g = m["human"]["geometry"]
    # labelled and not unsure: m1 (visible, flagged) m2 (visible, missed) c1 (none, flagged: geometry cannot dismiss) k1 (none) k2 (none, flagged)
    assert g["confusion"] == {"tp": 1, "fp": 2, "fn": 1, "tn": 1}
    assert g["precision"]["p"] == pytest.approx(1 / 3, abs=1e-4) and g["recall"]["p"] == 0.5
    assert g["clean_false_positive_rate"]["k"] == 1 and g["clean_false_positive_rate"]["n"] == 2
    d = m["human"]["diff"]                                                         # the pixels dismissed both false positives
    assert d["confusion"] == {"tp": 1, "fp": 0, "fn": 1, "tn": 3} and d["precision"]["p"] == 1.0
    assert m["labels"] == {"n": 6, "visible_defect": 2, "no_visible_defect": 3, "unsure": 1}
    assert m["headline"] is True                                                   # test split + labels


def test_a_development_run_is_never_a_headline_even_with_labels(tmp_path):
    run = write_run(tmp_path, split="dev")
    metrics.put_label(run, "m1", "visible_defect")
    m = metrics.compute(run)
    assert m["headline"] is False and any("development split" in c for c in m["caveats"])
    assert "NOT A HEADLINE" in metrics.render(m)


def test_wilson_interval_is_sane():
    lo, hi = metrics.wilson(0, 10)
    assert lo == 0 and 0.2 < hi < 0.35
    assert metrics.wilson(0, 0) == (0.0, 1.0)


# ----------------------------------------------------------------------------- the queue is stratified, seeded and blind
def test_queue_spreads_over_operators_and_is_reproducible(tmp_path):
    run = tmp_path / "r"
    (run / "cases").mkdir(parents=True)
    for op in ("fixed_width", "nudge", "badge_overlap"):
        for i in range(6):
            c = case(f"{op}-{i}", "mutated", {"geometry": [], "diff": []}, op)
            (run / "cases" / f"{c['id']}.json").write_text(json.dumps(c))
    for i in range(5):
        c = case(f"clean-{i}", "clean", {"geometry": [], "diff": []})
        (run / "cases" / f"{c['id']}.json").write_text(json.dumps(c))
    q1 = labelling.build_queue(run, n_mutated=9, n_clean=3, seed=3)
    assert len(q1) == 12 and sum(i.startswith("clean") for i in q1) == 3
    for op in ("fixed_width", "nudge", "badge_overlap"):
        assert sum(i.startswith(op) for i in q1) == 3
    assert labelling.build_queue(run, n_mutated=9, n_clean=3, seed=3) == q1


@pytest.fixture
def live(tmp_path):
    root = tmp_path / "root"
    (root / "targets").mkdir(parents=True)
    write_run(root / ".fixel" / "bench")
    with Live(create_app(root, db_path=tmp_path / "x.db", store_root=tmp_path / "art")) as lv:
        yield lv


def test_api_lists_runs_serves_a_blind_queue_and_records_labels(live):
    runs = live.http.get("/api/bench").json()
    assert runs["available"] and runs["runs"][0]["run"] == "r1" and runs["runs"][0]["split"] == "test"
    q = live.http.get("/api/bench/r1/queue").json()
    assert q["items"] and q["done"] == 0 and "visible layout defect" in q["question"]
    for item in q["items"]:                                    # blind: nothing that reveals the injection or Fixel's verdict
        assert not ({"op", "kind", "control", "levels", "scores", "baseline", "target_loc"} & set(item))
    cid = q["items"][0]["id"]
    assert live.http.put("/api/bench/r1/labels", json={"case_id": cid, "label": "visible_defect"}).status_code == 200
    assert live.http.put("/api/bench/r1/labels", json={"case_id": cid, "label": "maybe"}).status_code == 422
    assert live.http.put("/api/bench/r1/labels", json={"case_id": "nope", "label": "unsure"}).status_code == 404
    again = live.http.get("/api/bench/r1/queue").json()
    assert again["done"] == 1 and again["items"][0]["label"] == "visible_defect"
    assert live.http.get("/api/bench/r1").json()["labels"]["visible_defect"] == 1


def test_api_refuses_paths_outside_the_bench_directory(live):
    assert live.http.get("/api/bench/..%2F..").status_code == 404
    assert live.http.get("/api/bench/missing").status_code == 404
