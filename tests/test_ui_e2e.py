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


def row_for(page, loc_fragment):
    return page.locator('[data-testid=finding-row]').filter(has=page.locator('code', has_text=loc_fragment)).first


def test_scan_inspect_fix_and_refuse_a_bad_fix_across_pages(server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("FIXEL_CHROMIUM_PATH") or None)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        problems: list[str] = []
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.on("console", lambda m: m.type == "error" and problems.append(f"console: {m.text} {m.location.get('url', '')}"))

        # ----------------------------------------------------------------- home: nothing yet, three jobs one click away
        page.goto(server.url)
        expect(page.get_by_test_id("no-scans")).to_contain_text("No scans yet")
        expect(page.get_by_test_id("mode")).to_be_visible()
        shot(page, "01-home-empty")

        # ----------------------------------------------------------------- scan setup: three steps, one button
        page.get_by_test_id("action-scan").click()
        expect(page).to_have_url(re.compile(r"/scan$"))
        expect(page.get_by_test_id("target-demo-shop")).to_have_attribute("data-on", "true")   # the demo app is pre-selected
        expect(page.get_by_test_id("state-count")).to_have_text("6")                           # 3 widths x 2 themes x 1 text setting
        page.get_by_test_id("evidence-quick").click()                                          # no API spend in a test
        shot(page, "02-scan-setup")
        page.get_by_test_id("scan-button").click()

        # ----------------------------------------------------------------- the run page: progress, then findings
        expect(page).to_have_url(re.compile(r"/runs/[0-9a-f]+$"))
        run_url = page.url
        expect(page.get_by_test_id("count-confirmed")).to_have_text("3", timeout=120_000)
        expect(page.get_by_test_id("run-status")).to_have_text("Done", timeout=60_000)
        expect(page.get_by_test_id("finding-row")).to_have_count(3)
        shot(page, "03-run-findings")

        # every screen as a grid; counts per screen
        page.get_by_test_id("subnav-screens").click()
        expect(page.get_by_test_id("screen-320-light-none")).to_have_attribute("data-count", "3")  # card, chips, cookie banner
        expect(page.get_by_test_id("screen-1024-light-none")).to_have_attribute("data-count", "1")  # only the banner on desktop
        page.wait_for_function("() => [...document.querySelectorAll('[data-testid^=screen-] img')].every(i => i.complete && i.naturalWidth > 0)")
        shot(page, "04-screens")
        page.get_by_test_id("screen-320-light-none").click()
        expect(page.get_by_test_id("screen-finding")).to_have_count(3)
        expect(page.get_by_test_id("tile")).to_be_visible()
        page.get_by_test_id("back").click()
        page.get_by_test_id("subnav-findings").click()

        # statuses that are not "confirmed" are shown, not hidden
        page.get_by_test_id("tab-not_observable").click()
        expect(page.get_by_test_id("status-help")).to_contain_text("nothing visible changes")
        page.get_by_test_id("tab-confirmed").click()

        # ----------------------------------------------------------------- one finding, on its own page
        row_for(page, "PriceCard.jsx").click()
        expect(page.get_by_test_id("finding-title")).to_have_text("Runs off the screen")
        key = page.get_by_test_id("finding-page").get_attribute("data-key")
        chips = page.get_by_test_id("chips")
        expect(chips).to_contain_text("overflows by")
        expect(chips).to_contain_text("Pixels")
        expect(chips).to_contain_text("Spark unavailable — geometry and pixels only")
        expect(page.locator('[data-testid=finding-box][data-active=true]')).to_have_count(1)
        expect(page.get_by_test_id("scrubber-fail")).to_be_visible()                  # failing range shaded on the scrubber
        page.get_by_test_id("tile").hover()
        page.keyboard.press("1")                                                      # all page elements layer
        page.get_by_test_id("layers-button").click()
        expect(page.get_by_test_id("layer-dom")).to_have_attribute("data-on", "true")
        expect(page.get_by_test_id("overlay").locator("rect")).not_to_have_count(0)
        page.get_by_test_id("layer-dom").click()                                      # and off again, by mouse
        page.get_by_test_id("finding-title").click()                                  # closes the menu
        shot(page, "05-finding")
        page.keyboard.press("k")                                                      # previous finding has its own URL
        expect(page.get_by_test_id("finding-page")).not_to_have_attribute("data-key", key)
        page.keyboard.press("j")
        expect(page.get_by_test_id("finding-page")).to_have_attribute("data-key", key)

        # ----------------------------------------------------------------- fix #1: blocked edit, then a verified fix, on its own page
        page.get_by_test_id("fix-button").click()
        expect(page).to_have_url(re.compile(r"/fixes/[0-9a-f]+$"))
        expect(page.get_by_test_id("fix-status")).to_have_text("verified", timeout=240_000)
        expect(page.get_by_test_id("fix-model")).to_have_text("Wonder")
        expect(page.get_by_test_id("verdict")).to_have_attribute("data-ok", "true")
        expect(page.locator('[data-testid=step][data-state=done]')).to_have_count(4)
        proof = page.get_by_test_id("proof")                                          # the proof tab opens by itself at the end
        expect(proof.locator('[data-testid=check][data-state=ok]')).to_have_count(5)
        cells = proof.get_by_test_id("grid-cell")
        assert cells.count() == 6 and cells.evaluate_all("els => els.every(e => e.dataset.state === 'ok')")
        expect(proof.get_by_test_id("before-after")).to_be_visible()
        href = page.get_by_test_id("export").get_attribute("href")
        body = page.request.get(server.url + href)
        assert body.status == 200 and "max-w-full" in body.text() and "overflow-hidden" not in body.text()
        shot(page, "06-fix-verified")

        page.get_by_test_id("tab-changes").click()
        tabs = page.get_by_test_id("diff-tab")
        expect(tabs).to_have_count(3)                                                 # blocked edit, good edit, final patch
        assert tabs.nth(0).get_attribute("data-blocked") == "true" and tabs.nth(1).get_attribute("data-blocked") == "false"
        tabs.nth(0).click()
        expect(page.get_by_test_id("lint-reasons")).to_contain_text("hides or clips")
        expect(page.get_by_test_id("diff")).to_contain_text("overflow-hidden")
        shot(page, "07-fix-blocked-edit")
        tabs.nth(2).click()
        expect(page.get_by_test_id("diff").locator('[data-kind=add]')).to_have_count(1)

        page.get_by_test_id("tab-log").click()
        names = page.locator('[data-testid=timeline-row]').evaluate_all("els => els.map(e => e.dataset.name + ':' + e.dataset.status)")
        assert names[:4] == ["edit_file:blocked", "edit_file:ok", "rerender:ok", "finish:ok"], names

        page.get_by_test_id("back").click()
        expect(page.get_by_test_id("view-fix")).to_contain_text("Fixed ✓")

        # ----------------------------------------------------------------- fix #2: a bad fix must not be called fixed
        page.goto(run_url)
        expect(row_for(page, "PriceCard.jsx")).to_contain_text("Fixed ✓")
        row_for(page, "Perks.jsx").click()
        page.get_by_test_id("fix-button").click()
        expect(page.get_by_test_id("fix-status")).to_have_text("not verified", timeout=240_000)
        expect(page.get_by_test_id("not-verified")).to_be_visible()
        expect(page.get_by_test_id("export")).to_be_disabled()
        expect(page.locator('[data-testid=check][data-check=target_gone][data-state=fail]')).to_have_count(1)
        expect(page.locator('[data-testid=grid-cell][data-state=fail]').first).to_be_visible()
        shot(page, "08-fix-not-verified")

        # ----------------------------------------------------------------- every page is a URL rebuilt from the event log
        page.reload()
        expect(page.get_by_test_id("fix-status")).to_have_text("not verified", timeout=60_000)
        page.goto(run_url)
        expect(page.get_by_test_id("count-confirmed")).to_have_text("3", timeout=60_000)

        # ----------------------------------------------------------------- home now lists the unfinished work
        page.get_by_test_id("nav-home").click()
        expect(page.get_by_test_id("todo-findings")).to_contain_text("2 confirmed findings not fixed yet")
        expect(page.get_by_test_id("recent-run")).to_have_count(1)
        shot(page, "09-home")
        page.get_by_test_id("nav-runs").click()
        expect(page.get_by_test_id("run-row")).to_have_count(1)

        # ----------------------------------------------------------------- the benchmark page is honest
        page.get_by_test_id("nav-benchmark").click()
        expect(page.get_by_test_id("bench-none")).to_contain_text("no benchmark has been run yet")
        page.goto(server.url + "/no/such/page")
        expect(page.get_by_text("There is no page here")).to_be_visible()

        assert problems == [], problems
        browser.close()
