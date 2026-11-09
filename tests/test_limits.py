"""Public-mode rate limits and the daily model spend cap (api/limits.py)."""
import asyncio

from fastapi.testclient import TestClient

from fixel.api.limits import Limited, Limiter, Limits, Window
from fixel.api.server import create_app


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def test_window_slides():
    w = Window(2, 60)
    assert w.check("a", 0) is None and w.check("a", 1) is None
    assert w.check("a", 2) == 59                       # third within the minute waits for the first to expire
    assert w.check("b", 2) is None                     # other clients are separate
    assert w.check("a", 61) is None


def test_start_limits_per_kind_and_concurrency(tmp_path):
    clock = Clock()
    lim = Limiter(Limits(model_scans_per_hour=1, scans_per_hour=2, fixes_per_hour=1, daily_usd=1.0), tmp_path / "s.json", clock)
    lim.start("scan", "1.1.1.1", True, 0)
    try:
        lim.start("scan", "1.1.1.1", True, 0)
        raise AssertionError("second full check allowed")
    except Limited as e:
        assert e.status == 429 and e.retry_after and "full checks" in str(e)
    lim.start("scan", "1.1.1.1", False, 0)             # quick checks have their own allowance
    lim.start("scan", "2.2.2.2", True, 0)              # and so does another address
    try:
        lim.start("fix", "3.3.3.3", True, 1)
        raise AssertionError("ran two at once")
    except Limited as e:
        assert "another scan or fix" in str(e)
    clock.t += 3601
    lim.start("scan", "1.1.1.1", True, 0)


def test_daily_cap_persists_and_blocks_model_work_only(tmp_path):
    p = tmp_path / "spend.json"
    lim = Limiter(Limits(daily_usd=0.5), p)
    lim.spend.add(0.3)
    lim.spend.add(0.3)
    assert Limiter(Limits(daily_usd=0.5), p).spend.spent_today() == 0.6     # survives a restart
    try:
        lim.start("fix", "x", True, 0)
        raise AssertionError("fix allowed over the daily cap")
    except Limited as e:
        assert "budget" in str(e)
    lim.start("scan", "x", False, 0)                    # a quick check costs nothing and still runs


def test_client_ip_only_trusts_forwarded_header_when_told(tmp_path):
    h = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
    assert Limiter(Limits(), tmp_path / "a").client_ip(h, "10.0.0.1") == "10.0.0.1"
    assert Limiter(Limits(trust_proxy=True), tmp_path / "b").client_ip(h, "10.0.0.1") == "9.9.9.9"


def test_public_app_refuses_urls_label_writes_and_floods(tmp_path):
    app = create_app(tmp_path, db_path=tmp_path / "f.db", store_root=tmp_path / "art", config_roots=[tmp_path],
                     bench_root=tmp_path / "b", public=True, limits=Limits(requests_per_minute=5, run_budget_usd=0.25))
    c = TestClient(app)
    cfg = c.get("/api/config").json()
    assert cfg["public"] and cfg["budget_usd"] == 0.25 and cfg["limits"]["daily_usd"] == 5.0
    r = c.post("/api/scans", json={"base_url": "http://169.254.169.254/"})
    assert r.status_code == 403 and "arbitrary URL" in r.json()["detail"]
    assert c.put("/api/bench/x/labels", json={"case_id": "a", "label": "unsure"}).status_code == 403
    codes = [c.get("/api/config").status_code for _ in range(5)]
    assert codes[-1] == 429


def test_daily_cap_stops_running_work(tmp_path):
    app = create_app(tmp_path, db_path=tmp_path / "f.db", store_root=tmp_path / "art", config_roots=[tmp_path],
                     public=True, limits=Limits(daily_usd=0.0001))
    mgr = app.state.mgr
    ev = {"type": "model.call", "kind": "chat", "model": "muse-spark-1.3", "usage": {"input_tokens": 100000, "output_tokens": 10000}, "source": "live"}
    try:
        asyncio.run(mgr.emit("r1", ev))
    except Exception:
        pass                                             # the event log may want a real run; the cap is what is tested
    assert "r1" in mgr.stopped
    assert app.state.limiter.budget_left() == 0


def test_local_server_has_no_limits(tmp_path):
    app = create_app(tmp_path, db_path=tmp_path / "f.db", store_root=tmp_path / "art", config_roots=[tmp_path])
    c = TestClient(app)
    assert c.get("/api/config").json()["public"] is False
    assert all(c.get("/api/config").status_code == 200 for _ in range(300))
