"""The demo's fallback (guide section 14.1): scan, triage and three fixes of the planted-defect demo-shop, served entirely
from the committed recording in tests/demo_cache, with no API key and no model call. Everything else is real: Chromium renders
the app, the oracles, the opacity diff, the worktree, the linter and the model-free verifier run.

Refresh the recording (live calls on the synthetic demo app, a few cents) with:
    FIXEL_CACHE_DIR=tests/demo_cache FIXEL_MODE=record fixel scan --config targets/demo-shop.yaml
    FIXEL_CACHE_DIR=tests/demo_cache FIXEL_MODE=record fixel fix  --config targets/demo-shop.yaml --index N   (N = 1, 2, 3)
"""
import argparse
import asyncio
from pathlib import Path

import pytest

from fixel import config as cfg
from fixel.cli import run_fix, run_scan
from fixel.meta import client
from fixel.scan import findings_of
from fixel.verify.matrix import matrix_states

REPO = Path(__file__).resolve().parents[1]
RECORDING = REPO / "tests" / "demo_cache"
DEMO = REPO / "targets" / "demo-shop"

pytestmark = pytest.mark.skipif(not ((DEMO / "node_modules").exists() and RECORDING.exists()),
                                reason="run `make targets` first; tests/demo_cache is the committed recording")


@pytest.fixture
def offline(monkeypatch):
    """Replay mode on the recording, no key in the environment, and any attempt to reach a model is a failure."""
    monkeypatch.setenv("FIXEL_MODE", "replay")
    monkeypatch.setenv("FIXEL_CACHE_DIR", str(RECORDING))
    for name in ("MODEL_API_KEY", "META_MODEL_API"):
        monkeypatch.delenv(name, raising=False)

    def no_network():
        raise AssertionError("replay mode tried to create a model client")
    monkeypatch.setattr(client, "get_client", no_network)
    monkeypatch.chdir(REPO)
    before = sorted(p.name for p in RECORDING.rglob("*.json"))
    yield
    assert sorted(p.name for p in RECORDING.rglob("*.json")) == before, "replay must not write to the recording"


def demo_conf() -> cfg.Config:
    conf = cfg.load("targets/demo-shop.yaml")
    conf.target.path = str(DEMO)
    return conf


def test_scan_triage_and_all_three_fixes_replay_offline(offline, tmp_path):
    conf = demo_conf()
    results, triage = asyncio.run(run_scan(conf, conf.states(), None, lambda *_: None, models=True))
    findings = findings_of(results, triage)

    assert sorted(f.type for f in findings) == ["occlusion", "viewport_protrusion", "viewport_protrusion"]
    assert all(f.status == "confirmed" for f in findings)
    assert len(triage) == 3 and all(t.verdict == "real_defect" for t in triage.values()), "Spark's answers come from the recording"
    assert all(f.locs for f in findings), "every finding is localized to source"

    # one fix per planted defect, each verified by the model-free verifier over the whole width x theme matrix
    patched = {}
    for index in (1, 2, 3):
        args = argparse.Namespace(route=None, list=False, index=index, finding=None, model="muse-wonder-1.0", widths=None, themes=None,
                                  stress=None, offline=False, out=str(tmp_path / f"fix{index}"))
        assert asyncio.run(run_fix(demo_conf(), args)) == 0, f"fix {index} was not verified on replay"
        result = (tmp_path / f"fix{index}" / "result.json").read_text()
        assert '"status": "verified"' in result
        patched[index] = next((tmp_path / f"fix{index}").glob("*.patch")).read_text()

    assert "pb-36" in patched[1] and "src/App.jsx" in patched[1]                   # the cookie banner no longer covers Checkout
    assert "flex-wrap" in patched[2] and "Perks.jsx" in patched[2]                  # the chip row wraps
    assert "max-w-full" in patched[3] and "PriceCard.jsx" in patched[3]             # the card shrinks on a phone
    for diff in patched.values():
        assert "overflow-hidden" not in diff and "!important" not in diff and "display:none" not in diff.replace(" ", "")


def test_a_cache_miss_in_replay_raises_and_spends_nothing(offline):
    async def go():
        async def live():
            raise AssertionError("must not be called")
        return await client.call("spark.triage", {"img": "not-in-the-recording"}, live)
    with pytest.raises(client.CacheMiss):
        asyncio.run(go())
