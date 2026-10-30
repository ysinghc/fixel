"""The built UI, driven in a real browser against the real API and a real target (the planted-defect demo-shop).

The fix model is scripted so the run is deterministic and costs nothing; everything else is real: Chromium renders the
target, the oracles and the opacity diff run, the worktree and the verifier run. Set FIXEL_SHOTS=<dir> to keep screenshots.
"""
import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from fixel.api.server import create_app
from helpers import Live, Scripted

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "targets" / "demo-shop"
SHOTS = Path(os.environ["FIXEL_SHOTS"]) if os.environ.get("FIXEL_SHOTS") else None

pytestmark = pytest.mark.skipif(
    not ((REPO / "web" / "dist" / "index.html").exists() and (DEMO / "node_modules").exists()),
    reason="run `npm run build` in web/ and `make targets` first")

CARD_OLD = 'className="w-[480px] rounded-2xl border bg-white p-6"'
PERKS_OLD = 'className="flex flex-nowrap gap-2"'


def edit(path, old, new):
    return ("edit_file", {"path": path, "old": old, "new": new})


# fix 1 (the 480px card): a symptom-hiding edit the linter must bounce, then the real fix, then finish
FIX_CARD = [
    [edit("src/components/PriceCard.jsx", CARD_OLD, 'className="w-[480px] overflow-hidden rounded-2xl border bg-white p-6"')],
    [edit("src/components/PriceCard.jsx", CARD_OLD, 'className="w-[480px] max-w-full rounded-2xl border bg-white p-6"')],
    [("rerender", {})],
    [("finish", {"summary": "The card keeps 480px on wide screens and shrinks to fit a phone."})],
]
# fix 2 (the chip row): an edit that does not help, so the verifier must refuse to call it fixed
FIX_PERKS = [
    [edit("src/components/Perks.jsx", PERKS_OLD, 'className="flex flex-nowrap gap-3"')],
    [("finish", {"summary": "Spaced the chips out."})],
    [("finish", {"summary": "Still spaced out."})],
    [("finish", {"summary": "Done."})],
]


@pytest.fixture
def server(tmp_path):
    cfgs = tmp_path / "configs"
    cfgs.mkdir()
    (cfgs / "demo.yaml").write_text(
        f"target:\n  name: demo-shop\n  split: demo\n  path: {DEMO}\nroutes: [/]\n"
        "matrix:\n  widths: [320, 375, 1024]\n  themes: [light, dark]\n  text_stress: [none]\n  height: 600\n")
    scripts = iter([FIX_CARD, FIX_PERKS])
    app = create_app(REPO, db_path=tmp_path / "fixel.db", store_root=tmp_path / "art", config_roots=[cfgs], bench_root=tmp_path / "no-bench",
                     llm_factory=lambda model, fallback, emit: Scripted(next(scripts), model))
    with Live(app) as live:
        yield live


def shot(page, name):
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"{name}.png"))


def card_for(page, loc_fragment):
    return page.locator('[data-testid=finding-card]').filter(has=page.locator('code', has_text=loc_fragment)).first


def test_scan_inspect_fix_and_refuse_a_bad_fix_in_the_browser(server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("FIXEL_CHROMIUM_PATH") or None)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        problems: list[str] = []
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.on("console", lambda m: m.type == "error" and problems.append(f"console: {m.text} {m.location.get('url', '')}"))

        page.goto(server.url)
        expect(page.get_by_test_id("empty")).to_contain_text("No scan yet")
        expect(page.get_by_test_id("target-select")).to_have_value(re.compile("demo.yaml"))
        expect(page.get_by_test_id("mode")).to_be_visible()
        shot(page, "01-empty")

        # ----------------------------------------------------------------- scan
        page.get_by_test_id("models-toggle").uncheck()                       # no API spend in a test
        page.get_by_test_id("scan-button").click()
        expect(page.get_by_test_id("count-confirmed")).to_have_text("3", timeout=120_000)
        for w in (320, 375, 1024):
            expect(page.get_by_test_id(f"width-{w}")).to_be_enabled()
        shot(page, "02-scanned")
        expect(page.get_by_test_id("width-count-320")).to_have_text("3")        # card + chips + cookie banner at a phone width
        expect(page.get_by_test_id("width-count-1024")).to_have_text("1")       # only the banner still covers the button on desktop

        # ----------------------------------------------------------------- inspect a finding
        card = card_for(page, "PriceCard.jsx")
        card.click()
        expect(card).to_have_attribute("data-selected", "true")
        expect(page.locator('[data-testid=finding-box][data-active=true]')).to_have_count(1)
        expect(page.get_by_test_id("scrubber-fail")).to_be_visible()             # failing range shaded on the scrubber
        expect(card.get_by_test_id("chips")).to_contain_text("Geometry: overflows by")
        expect(card.get_by_test_id("chips")).to_contain_text("Pixels:")
        expect(card.get_by_test_id("chips")).to_contain_text("Spark unavailable — geometry and pixels only")
        expect(card.locator("code")).to_have_text("PriceCard.jsx:4")
        page.get_by_test_id("tile").hover()
        page.keyboard.press("1")                                                  # DOM boxes layer
        expect(page.get_by_test_id("layer-dom")).to_have_attribute("data-on", "true")
        expect(page.get_by_test_id("overlay").locator("rect")).not_to_have_count(0)
        shot(page, "03-selected-with-dom-layer")
        page.keyboard.press("1")
        page.keyboard.press("k")                                                  # previous finding (the card is last in the list)
        expect(card).to_have_attribute("data-selected", "false")
        page.keyboard.press("j")
        expect(card).to_have_attribute("data-selected", "true")

        # statuses that are not "confirmed" are shown, not hidden
        page.get_by_test_id("tab-not_observable").click()
        expect(page.get_by_test_id("findings")).to_be_visible()
        page.get_by_test_id("tab-confirmed").click()

        # ----------------------------------------------------------------- fix #1: blocked edit, then a verified fix
        card.get_by_test_id("fix-button").click()
        drawer = page.get_by_test_id("drawer")
        expect(drawer).to_be_visible(timeout=30_000)
        expect(page.get_by_test_id("fix-status")).to_have_text("verified", timeout=240_000)
        expect(page.get_by_test_id("fix-model")).to_have_text("Wonder")
        names = page.locator('[data-testid=timeline-row]').evaluate_all("els => els.map(e => e.dataset.name + ':' + e.dataset.status)")
        assert names[:4] == ["edit_file:blocked", "edit_file:ok", "rerender:ok", "finish:ok"], names
        expect(drawer.get_by_test_id("lint-reasons")).to_have_count(0)            # shown only on the blocked tab
        tabs = page.get_by_test_id("diff-tab")
        expect(tabs).to_have_count(3)                                             # blocked edit, good edit, final patch
        assert tabs.nth(0).get_attribute("data-blocked") == "true" and tabs.nth(1).get_attribute("data-blocked") == "false"
        tabs.nth(0).click()
        expect(drawer.get_by_test_id("lint-reasons")).to_contain_text("hides or clips")
        expect(drawer.get_by_test_id("diff")).to_contain_text("overflow-hidden")
        shot(page, "04-blocked-edit")
        tabs.nth(2).click()
        expect(drawer.get_by_test_id("diff")).to_contain_text("max-w-full")
        expect(drawer.get_by_test_id("diff").locator('[data-kind=add]')).to_have_count(1)
        # proof: every checklist item, every grid cell, a before/after slider, and an enabled export
        expect(drawer.locator('[data-testid=check][data-state=ok]')).to_have_count(5)
        cells = drawer.get_by_test_id("grid-cell")
        assert cells.count() == 6 and cells.evaluate_all("els => els.every(e => e.dataset.state === 'ok')")
        expect(drawer.get_by_test_id("before-after")).to_be_visible()
        export = drawer.get_by_test_id("export")
        expect(export).to_be_visible()
        href = export.get_attribute("href")
        body = page.request.get(server.url + href)
        assert body.status == 200 and "max-w-full" in body.text() and "overflow-hidden" not in body.text()
        shot(page, "05-fix-verified")
        expect(card).to_contain_text("Fixed ✓")

        # ----------------------------------------------------------------- fix #2: a bad fix must not be called fixed
        card2 = card_for(page, "Perks.jsx")
        card2.click()
        card2.get_by_test_id("fix-button").click()
        expect(page.get_by_test_id("fix-status")).to_have_text("not verified", timeout=240_000)
        expect(drawer.get_by_test_id("not-verified")).to_be_visible()
        expect(drawer.get_by_test_id("export")).to_be_disabled()
        expect(drawer.locator('[data-testid=check][data-check=target_gone][data-state=fail]')).to_have_count(1)
        expect(drawer.locator('[data-testid=grid-cell][data-state=fail]').first).to_be_visible()
        shot(page, "06-fix-not-verified")
        page.keyboard.press("Escape")
        expect(drawer).to_have_count(0)

        # ----------------------------------------------------------------- the screen is a function of the event log
        page.reload()
        expect(page.get_by_test_id("count-confirmed")).to_have_text("3", timeout=60_000)
        expect(page.get_by_test_id("width-count-320")).to_be_visible()
        expect(card_for(page, "PriceCard.jsx")).to_contain_text("Fixed ✓")        # the fix was rebuilt from the same stream
        shot(page, "07-after-reload")

        # ----------------------------------------------------------------- the benchmark tab is honest
        page.get_by_test_id("tab-bench").click()
        expect(page.get_by_test_id("bench")).to_contain_text("Not available yet")
        page.get_by_test_id("tab-scan").click()

        assert problems == [], problems
        browser.close()
