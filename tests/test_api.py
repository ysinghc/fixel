"""The API: durable events, replay without gaps or repeats, real scans, fix sessions, artifacts, labels, the budget cap."""
import asyncio
import json
import urllib.parse
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from fixel.api.db import DB
from fixel.api.runs import RunManager
from fixel.api.server import create_app
from fixel.scan import serve_static
from fixel.store import ArtifactStore
from helpers import Live, Scripted, git

SITE = Path(__file__).parent / "fixtures" / "site"
PROMO = ".promo{width:480px;background:#fde;padding:12px}"
GOOD = ".promo{width:100%;max-width:480px;background:#fde;padding:12px}"


def write_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "targets").mkdir(parents=True)
    (root / "fixel.yaml").write_text("target:\n  name: fixture\n  split: demo\nroutes: [/index.html, /checkout.html]\n"
                                     "matrix:\n  widths: [320, 1024]\n  themes: [light]\n  text_stress: [none]\n")
    return root


@pytest.fixture
def live(tmp_path):
    root = write_root(tmp_path)
    with Live(create_app(root, db_path=tmp_path / "fixel.db", store_root=tmp_path / "art")) as lv:
        yield lv


@pytest.fixture
def site():
    server, url = serve_static(SITE)
    yield url
    server.shutdown()


def scan(live, site, **kw):
    body = {"config": "fixel.yaml", "routes": ["/index.html"], "models": False, "base_url": site, **kw}
    r = live.http.post("/api/scans", json=body)
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


# ----------------------------------------------------------------------------- the durable event log
def test_events_get_sequence_numbers_and_survive_a_restart(tmp_path):
    db = DB(tmp_path / "x.db")
    rid = db.create_run("scan", {})
    evs = [db.append_event(rid, {"type": "a", "n": i}) for i in range(5)]
    assert [e["seq"] for e in evs] == [1, 2, 3, 4, 5]
    assert [e["seq"] for e in db.events(rid, after=3)] == [4, 5]
    assert DB(tmp_path / "x.db").events(rid)[2]["n"] == 2                       # a new connection to the same file sees it
    assert db.append_event(db.create_run("scan", {}), {"type": "b"})["seq"] == 1       # sequences are per run


async def test_a_subscriber_sees_each_event_once_and_late_ones_replay_history(tmp_path):
    mgr = RunManager(DB(":memory:"), ArtifactStore(tmp_path), tmp_path)
    rid = mgr.db.create_run("scan", {})
    await mgr.emit(rid, {"type": "early"})
    q = mgr.subscribe(rid)
    await mgr.emit(rid, {"type": "live1"})
    await mgr.emit(rid, {"type": "live2"})
    assert [q.get_nowait()["type"] for _ in range(2)] == ["live1", "live2"]
    assert [e["type"] for e in mgr.db.events(rid)] == ["early", "live1", "live2"]       # a late joiner gets all three from the log
    mgr.unsubscribe(rid, q)
    await mgr.emit(rid, {"type": "after"})
    assert q.empty()


async def test_the_budget_cap_stops_new_work_and_is_reported_once(tmp_path):
    mgr = RunManager(DB(":memory:"), ArtifactStore(tmp_path), tmp_path, budget_usd=1.0)
    rid = mgr.db.create_run("scan", {})
    call = {"type": "model.call", "kind": "spark.triage", "model": "muse-spark-1.3", "source": "live",
            "usage": {"input_tokens": 600_000, "output_tokens": 0}}                     # $0.75
    first = await mgr.emit(rid, call)
    assert first["usd"] == pytest.approx(0.75) and rid not in mgr.stopped
    second = await mgr.emit(rid, call)
    assert second["total_usd"] == pytest.approx(1.5) and rid in mgr.stopped
    await mgr.emit(rid, call)
    assert [e["type"] for e in mgr.db.events(rid)].count("budget.exceeded") == 1
    cached = await mgr.emit(rid, {**call, "source": "cached"})
    assert cached["usd"] == 0                                                           # a cached answer costs nothing


def test_prices(tmp_path):
    from fixel.cost import usd
    assert usd("sam.box", None, {"images": 1}) == pytest.approx(0.0025)
    assert usd("fix.turn", "muse-wonder-1.0", {"input_tokens": 1_000_000, "input_tokens_details": {"cached_tokens": 500_000},
                                               "output_tokens": 100_000}) == pytest.approx(0.5 * 4 + 0.5 * 0.2 + 0.1 * 20)
    assert usd("x", "unknown-model", {"input_tokens": 5}) == 0 and usd("sam.box", None, None) == 0


# ----------------------------------------------------------------------------- a real scan through the API
def test_a_scan_streams_every_stage_and_persists_what_the_ui_needs(live, site):
    rid = scan(live, site)
    done = live.wait(rid, "run.done")
    assert done["status"] == "done" and done["states"] == 2
    evs = live.events(rid)
    types = [e["type"] for e in evs]
    assert types[0] == "run.started" and types[-1] == "run.done"
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))                      # gapless, in order
    for t in ("state.started", "state.captured", "state.done", "candidate.found", "pixels.done", "finding.updated"):
        assert t in types, t
    # every state is announced before it is captured, and candidates arrive after their state
    cap = next(e for e in evs if e["type"] == "state.captured")
    assert cap["tiles"] and cap["tiles"][0]["sha"] and cap["vw"] == cap["width"]
    first_cand = next(e for e in evs if e["type"] == "candidate.found")
    assert first_cand["defect"] in ("viewport_protrusion", "small_target", "contrast", "collision", "occlusion", "clipped_text")
    assert first_cand["elements"] and len(first_cand["elements"][0]["rect"]) == 4

    run = live.http.get(f"/api/runs/{rid}").json()
    assert run["status"] == "done" and run["summary"]["counts"]["confirmed"] >= 3
    keys = {f["key"] for f in run["findings"]}
    assert any(k.startswith("viewport_protrusion|") for k in keys)

    # tile screenshots are served by content hash; the per-state detail has the DOM elements for the overlay
    png = live.http.get(f"/api/artifacts/{cap['tiles'][0]['sha']}")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"
    detail = live.http.get(f"/api/runs/{rid}/states/{cap['state_key']}").json()
    assert detail["capture"]["tiles"][0]["elements"] and len(detail["candidates"]) == len(detail["evidence"])


def test_reconnecting_with_after_loses_no_event_and_repeats_none(live, site):
    rid = scan(live, site)
    live.wait(rid, "run.done")
    everything = live.events(rid)
    mid = everything[len(everything) // 2]["seq"]
    rest = live.events(rid, after=mid)
    assert [e["seq"] for e in rest] == [e["seq"] for e in everything if e["seq"] > mid]
    # the browser's own reconnect header does the same
    r = live.http.get(f"/api/runs/{rid}/events", params={"follow": "false"}, headers={"Last-Event-ID": str(mid)})
    assert [json.loads(l[6:])["seq"] for l in r.text.splitlines() if l.startswith("data: ")] == [e["seq"] for e in rest]
    assert "id: " in r.text


def test_a_live_stream_delivers_events_as_they_happen_and_a_reconnect_resumes(live, site):
    rid = scan(live, site, routes=["/index.html", "/checkout.html"])
    first: list[dict] = []
    with live.http.stream("GET", f"/api/runs/{rid}/events", params={"after": 0}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                first.append(json.loads(line[6:]))
                if len(first) >= 6:
                    break                                                               # drop the connection mid-run
    resumed: list[dict] = []
    with live.http.stream("GET", f"/api/runs/{rid}/events", params={"after": first[-1]["seq"]}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                resumed.append(json.loads(line[6:]))
                if resumed[-1]["type"] == "run.done":
                    break
    seqs = [e["seq"] for e in first + resumed]
    assert seqs == list(range(1, len(seqs) + 1))                                        # no gap, no repeat across the reconnect
    assert [e["seq"] for e in live.events(rid)] == seqs


def test_a_scan_can_be_cancelled(live, site):
    rid = scan(live, site, routes=["/index.html", "/checkout.html"], widths=[320, 375, 414, 768, 1024, 1280, 1440])
    assert live.http.post(f"/api/runs/{rid}/cancel").json() == {"cancelled": True}
    assert live.wait(rid, "run.done")["status"] == "cancelled"
    assert live.http.get(f"/api/runs/{rid}").json()["status"] == "cancelled"
    assert live.http.post(f"/api/runs/{rid}/cancel").status_code == 409                 # nothing left to cancel


# ----------------------------------------------------------------------------- validation and the rest
def test_configs_outside_the_allowed_set_are_refused(live, tmp_path):
    (tmp_path / "outside.yaml").write_text("routes: [/]\n")                          # a real config, but not under the root
    for bad in ("../../etc/passwd", "/etc/passwd", "nope.yaml", "../outside.yaml", str(tmp_path / "outside.yaml")):
        r = live.http.post("/api/scans", json={"config": bad, "models": False})
        assert r.status_code == 404, bad


def test_targets_and_config(live):
    t = live.http.get("/api/targets").json()
    assert t[0]["name"] == "fixture" and t[0]["split"] == "demo" and t[0]["routes"] == ["/index.html", "/checkout.html"]
    c = live.http.get("/api/config").json()
    assert c["mode"] in ("live", "record", "replay") and "models_available" in c and c["budget_usd"] == 10.0


def test_artifacts_only_serve_content_hashes_that_exist(live):
    assert live.http.get("/api/artifacts/../../etc/passwd").status_code in (400, 404)
    assert live.http.get("/api/artifacts/nothex").status_code == 400
    assert live.http.get("/api/artifacts/" + "0" * 64).status_code == 404


def test_labels_are_validated_and_stored(live, site):
    rid = scan(live, site)
    live.wait(rid, "run.done")
    key = live.http.get(f"/api/runs/{rid}").json()["findings"][0]["key"]
    ok = live.http.post("/api/labels", json={"run_id": rid, "key": key, "label": "no_visible_defect", "note": "decorative"})
    assert ok.status_code == 200
    assert live.http.get("/api/labels", params={"run_id": rid}).json()[0]["label"] == "no_visible_defect"
    assert live.http.post("/api/labels", json={"run_id": rid, "key": key, "label": "maybe"}).status_code == 422
    assert live.http.post("/api/labels", json={"run_id": rid, "key": "nope", "label": "unsure"}).status_code == 404
    detail = live.http.get("/api/findings/" + urllib.parse.quote(key, safe=""), params={"run_id": rid}).json()   # keys contain | # : /
    assert detail["key"] == key and detail["label"]["label"] == "no_visible_defect"


def test_unbuilt_features_say_so_plainly(live):
    assert live.http.post("/api/voice").status_code == 501
    b = live.http.get("/api/bench").json()
    assert b["available"] is False and "not built" in b["reason"]


def test_a_bare_url_scan_has_nothing_to_fix(live, site):
    rid = scan(live, site)
    live.wait(rid, "run.done")
    key = next(f["key"] for f in live.http.get(f"/api/runs/{rid}").json()["findings"] if f["status"] == "confirmed")
    r = live.http.post("/api/fix", json={"run_id": rid, "key": key})
    assert r.status_code == 409 and "nothing to fix" in r.json()["detail"]
    assert live.http.post("/api/fix", json={"run_id": rid, "key": "nope"}).status_code == 404
    assert live.http.post("/api/fix", json={"run_id": "nope", "key": key}).status_code == 404


# ----------------------------------------------------------------------------- a fix session through the API
def edit(old, new):
    return ("edit_file", {"path": "index.html", "old": old, "new": new})


def fix_server(tmp_path, steps):
    root = tmp_path / "root"
    (root / "targets").mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copy(SITE / "index.html", repo / "index.html")
    git(repo, "init", "-q"); git(repo, "add", "."); git(repo, "commit", "-qm", "base")
    (root / "targets" / "demo.yaml").write_text(
        f"target:\n  name: demo\n  split: demo\n  path: {repo}\n  build_cmd: null\n"
        f"  dev_cmd: \"{sys.executable} -m http.server {{port}} --bind 127.0.0.1\"\n"
        "routes: [/index.html]\nmatrix:\n  widths: [320, 1024]\n  themes: [light]\n  text_stress: [none]\n")
    scripts = iter(steps)
    app = create_app(root, db_path=tmp_path / "fixel.db", store_root=tmp_path / "art",
                     llm_factory=lambda model, fallback, emit: Scripted(next(scripts), model))
    return Live(app), repo


def test_a_fix_session_streams_its_work_and_exports_only_a_verified_patch(tmp_path):
    good = [[edit(PROMO, ".promo{width:480px;background:#fde;padding:12px;overflow:hidden}")],      # blocked by the linter
            [edit(PROMO, GOOD)], [("rerender", {})], [("finish", {"summary": "shrinks to fit"})]]
    lv, repo = fix_server(tmp_path, [good])
    with lv as live:
        rid = live.http.post("/api/scans", json={"config": "targets/demo.yaml", "models": False}).json()["run_id"]
        assert live.wait(rid, "run.done")["status"] == "done"
        key = next(f["key"] for f in live.http.get(f"/api/runs/{rid}").json()["findings"]
                   if f["type"] == "viewport_protrusion" and f["status"] == "confirmed")
        fix_id = live.http.post("/api/fix", json={"run_id": rid, "key": key, "model": "muse-wonder-1.0"}).json()["fix_id"]
        res = live.wait(rid, "fix.result", timeout=240)
        assert res["status"] == "verified" and res["fix_id"] == fix_id and res["model"] == "muse-wonder-1.0"

        evs = [e for e in live.events(rid) if e.get("fix_id") == fix_id]
        types = [e["type"] for e in evs]
        assert types[0] == "fix.started" and "fix.baseline" in types and types[-1] == "fix.result"
        assert any(e["type"] == "fix.patch" and e["lint"] for e in evs) and any(e["type"] == "fix.patch" and not e["lint"] for e in evs)
        assert [e["item"] for e in evs if e["type"] == "fix.verify"] == ["lint", "target_gone", "no_new_findings", "no_drift", "build"]
        # the proof grid fills cell by cell, and the timeline learns what each tool call returned
        cells = {e["state_key"]: e["ok"] for e in evs if e["type"] == "fix.verify.state"}
        assert set(cells) == set(res["states"]) and all(cells.values())
        results = [e for e in evs if e["type"] == "fix.tool.result"]
        assert any(e["name"] == "edit_file" and e.get("blocked") and "clipping" in e["detail"] for e in results)
        assert any(e["name"] == "edit_file" and e["ok"] and e["detail"] == "applied" for e in results)
        assert any(e["name"] == "rerender" and e["ok"] and "defect gone in" in e["detail"] for e in results)
        assert any(e["type"] == "fix.verifying" for e in evs)

        # the proof pane needs: a pass/fail per state, and a before and after screenshot for each
        v = res["verification"]
        assert v["target_gone"] and all(v["grid"].values()) and set(v["grid"]) == set(res["states"])
        assert set(res["before_shots"]) == set(v["shots"]) == set(res["states"])
        assert all(live.http.get(f"/api/artifacts/{sha}").status_code == 200 for sha in v["shots"].values())
        assert len(res["attempts"]) == 1 and res["attempts"][0]["verification"]["target_gone"]

        patch = live.http.get(f"/api/fixes/{fix_id}/patch")
        assert patch.status_code == 200 and patch.text == res["diff"] and "max-width:480px" in patch.text
        assert "attachment" in patch.headers["content-disposition"]
        assert live.http.get(f"/api/fixes/{fix_id}").json()["status"] == "verified"
        assert "max-width" not in (repo / "index.html").read_text()                          # the user's repo is untouched


def test_an_unverified_fix_exports_no_patch(tmp_path):
    bad = [[edit(PROMO, ".promo{width:420px;background:#fde;padding:12px}")], [("finish", {"summary": "done"})],
           [("finish", {"summary": "still done"})], [("finish", {"summary": "really"})]]          # 420px still overflows a phone
    lv, _ = fix_server(tmp_path, [bad])
    with lv as live:
        rid = live.http.post("/api/scans", json={"config": "targets/demo.yaml", "models": False}).json()["run_id"]
        live.wait(rid, "run.done")
        key = next(f["key"] for f in live.http.get(f"/api/runs/{rid}").json()["findings"] if f["type"] == "viewport_protrusion")
        fix_id = live.http.post("/api/fix", json={"run_id": rid, "key": key}).json()["fix_id"]
        res = live.wait(rid, "fix.result", timeout=240)
        assert res["status"] == "failed" and not res["verification"]["target_gone"]
        r = live.http.get(f"/api/fixes/{fix_id}/patch")
        assert r.status_code == 409 and "not verified" in r.json()["detail"]


def test_a_non_confirmed_finding_cannot_be_fixed(tmp_path):
    lv, _ = fix_server(tmp_path, [[]])
    with lv as live:
        rid = live.http.post("/api/scans", json={"config": "targets/demo.yaml", "models": False}).json()["run_id"]
        live.wait(rid, "run.done")
        db = live.app.state.mgr.db
        f = db.findings(rid)[0]
        db.put_findings(rid, [{**f, "status": "dismissed"}])
        r = live.http.post("/api/fix", json={"run_id": rid, "key": f["key"]})
        assert r.status_code == 409 and "only confirmed" in r.json()["detail"]
