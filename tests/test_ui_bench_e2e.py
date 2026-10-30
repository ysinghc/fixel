"""The Label and Benchmark tabs in a real browser: blind labelling, labels that persist, measured numbers only."""
import json
import os
import re
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import expect, sync_playwright

from fixel.api.server import create_app
from fixel.store import ArtifactStore
from helpers import Live
from test_bench_metrics import write_run

REPO = Path(__file__).resolve().parents[1]
SHOTS = Path(os.environ["FIXEL_SHOTS"]) if os.environ.get("FIXEL_SHOTS") else None
pytestmark = pytest.mark.skipif(not (REPO / "web" / "dist" / "index.html").exists(), reason="run `npm run build` in web/ first")


def shot(page, name):
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"{name}.png"))


def with_screens(run: Path, store: ArtifactStore):
    """Give every case two real screenshots so the labelling view has something to show."""
    for p in (run / "cases").glob("*.json"):
        c = json.loads(p.read_text())
        tiles = []
        for n, colour in enumerate(((240, 240, 245), (225, 235, 245))):
            path = run / f"{n}.png"
            Image.new("RGB", (320, 600), colour).save(path)
            tiles.append(store.put(path.read_bytes()))
        c["tiles"] = tiles
        p.write_text(json.dumps(c))


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "root"
    (root / "targets").mkdir(parents=True)
    store = ArtifactStore(tmp_path / "art")
    run = write_run(root / ".fixel" / "bench")
    with_screens(run, store)
    with Live(create_app(root, db_path=tmp_path / "x.db", store_root=tmp_path / "art", web_dist=REPO / "web" / "dist")) as lv:
        yield lv


@pytest.fixture
def empty_server(tmp_path):
    root = tmp_path / "root"
    (root / "targets").mkdir(parents=True)
    with Live(create_app(root, db_path=tmp_path / "x.db", store_root=tmp_path / "art", web_dist=REPO / "web" / "dist")) as lv:
        yield lv


def test_benchmark_tab_says_nothing_was_measured_when_nothing_was(empty_server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("FIXEL_CHROMIUM_PATH") or None)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(empty_server.url)
        page.get_by_test_id("tab-bench").click()
        expect(page.get_by_test_id("bench-none")).to_contain_text("no benchmark has been run yet")
        expect(page.get_by_test_id("human")).to_have_count(0)                        # no table, no invented numbers
        page.get_by_test_id("tab-label").click()
        expect(page.get_by_test_id("label-view")).to_contain_text("Nothing to label yet")
        browser.close()


def test_blind_labelling_persists_and_feeds_the_benchmark_tab(server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("FIXEL_CHROMIUM_PATH") or None)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        problems = []
        page.on("pageerror", lambda e: problems.append(str(e)))
        page.on("console", lambda m: m.type == "error" and problems.append(f"{m.text} {m.location.get('url', '')}"))
        page.goto(server.url)

        # ------------------------------------------------------------- before any label: no human numbers
        page.get_by_test_id("tab-bench").click()
        expect(page.get_by_test_id("no-labels")).to_be_visible()
        expect(page.get_by_test_id("caveats")).to_contain_text("injected")
        expect(page.get_by_text("not a headline result")).to_be_visible()

        # ------------------------------------------------------------- the labelling view is blind
        page.get_by_test_id("tab-label").click()
        view = page.get_by_test_id("label-view")
        expect(page.get_by_test_id("label-progress")).to_have_text("0 / 7 labelled")
        expect(page.get_by_test_id("label-tile")).to_have_count(2)
        text = view.inner_text()
        for secret in ("fixed_width", "nudge", "badge_overlap", "mutated", "injected", "unmodified", "viewport_protrusion", "a.jsx"):
            assert secret not in text, f"the labelling view leaked '{secret}'"
        expect(page.get_by_test_id("label-meta")).to_contain_text("320px")
        shot(page, "10-label")

        # v, n, u record labels and move on; a label can be changed by going back
        page.keyboard.press("v")
        expect(page.get_by_test_id("label-progress")).to_have_text("1 / 7 labelled")
        page.keyboard.press("n")
        page.keyboard.press("u")
        expect(page.get_by_test_id("label-progress")).to_have_text("3 / 7 labelled")
        page.keyboard.press("ArrowLeft")
        expect(page.get_by_test_id("label-u")).to_have_attribute("data-on", "true")
        page.get_by_test_id("label-n").click()
        expect(page.locator('[data-testid=label-item][data-label=no_visible_defect]')).to_have_count(2)

        # ------------------------------------------------------------- labels survive a reload
        page.reload()
        page.get_by_test_id("tab-label").click()
        expect(page.get_by_test_id("label-progress")).to_have_text("3 / 7 labelled")

        # ------------------------------------------------------------- label everything, then the numbers appear
        for _ in range(4):
            page.keyboard.press("v")
        expect(page.get_by_test_id("label-progress")).to_have_text("7 / 7 labelled")
        page.get_by_test_id("tab-bench").click()
        expect(page.get_by_test_id("human-table")).to_be_visible()
        rows = page.locator('[data-testid=human-table] tbody tr')
        expect(rows).to_have_count(2)                                                  # geometry and + opacity diff
        expect(rows.first).to_contain_text("Geometry")
        expect(page.get_by_text("headline result", exact=True)).to_be_visible()         # test split + human labels
        expect(page.get_by_test_id("agreement")).to_contain_text("Not detection accuracy")
        expect(page.get_by_test_id("construction")).to_contain_text("Ghost banner")
        shot(page, "11-benchmark")
        assert problems == [], problems
        browser.close()
