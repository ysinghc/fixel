"""Accessibility audit of every page of the built UI with axe-core (WCAG 2.1 A/AA), against a real scan of demo-shop.

Any serious or critical violation fails. Also checks a few things axe does not: one <main>, a skip link, every
interactive element reachable with a visible focus ring, and no horizontal scroll at phone width.
"""
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from fixel.api.server import create_app
from helpers import Live

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "targets" / "demo-shop"
AXE = REPO / "node_modules" / "axe-core" / "axe.min.js"
BENCH = REPO / ".fixel" / "bench"

pytestmark = pytest.mark.skipif(
    not ((REPO / "web" / "dist" / "index.html").exists() and (DEMO / "node_modules").exists() and AXE.exists()),
    reason="run `make web`, `make targets` and `make install` first")


@pytest.fixture
def server(tmp_path):
    cfgs = tmp_path / "configs"
    cfgs.mkdir()
    (cfgs / "demo.yaml").write_text(
        f"target:\n  name: demo-shop\n  split: demo\n  path: {DEMO}\nroutes: [/]\n"
        "matrix:\n  widths: [320, 1024]\n  themes: [light]\n  text_stress: [none]\n  height: 600\n")
    app = create_app(REPO, db_path=tmp_path / "fixel.db", store_root=tmp_path / "art", config_roots=[cfgs],
                     bench_root=BENCH if BENCH.exists() else tmp_path / "no-bench")
    with Live(app) as live:
        yield live


def audit(page, name):
    page.wait_for_load_state("networkidle")
    page.add_script_tag(path=str(AXE))
    res = page.evaluate("""() => axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}})""")
    bad = [f"{name}: [{v['impact']}] {v['id']}: {v['help']} -> {[n['target'] for n in v['nodes'][:3]]}"
           for v in res["violations"] if v["impact"] in ("serious", "critical")]
    mains = page.locator("main").count()
    if mains != 1:
        bad.append(f"{name}: {mains} <main> elements")
    return bad


def test_every_page_passes_axe(server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("FIXEL_CHROMIUM_PATH") or None)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        bad: list[str] = []
        page.goto(server.url)
        bad += audit(page, "home-empty")
        page.get_by_test_id("action-scan").click()
        bad += audit(page, "scan")
        page.get_by_test_id("evidence-quick").click()
        page.get_by_test_id("scan-button").click()
        expect(page.get_by_test_id("run-status")).to_have_text("Done", timeout=180_000)
        run_url = page.url
        bad += audit(page, "run")
        page.get_by_test_id("subnav-screens").click()
        bad += audit(page, "screens")
        page.locator("[data-testid^=screen-]").first.click()
        bad += audit(page, "screen")
        page.goto(run_url)
        page.get_by_test_id("finding-row").first.click()
        expect(page.get_by_test_id("finding-title")).to_be_visible()
        bad += audit(page, "finding")
        for path, name in [("/runs", "runs"), ("/", "home"), ("/label", "label"), ("/benchmark", "benchmark"), ("/nope", "404")]:
            page.goto(server.url + path)
            bad += audit(page, name)

        # keyboard: the first Tab lands on a skip link that moves focus to the main content
        page.goto(server.url)
        page.keyboard.press("Tab")
        if "Skip to content" not in (page.evaluate("document.activeElement.textContent") or ""):
            bad.append("first Tab does not reach a skip link")
        else:
            page.keyboard.press("Enter")
            if page.evaluate("document.activeElement.id") != "main":
                bad.append("skip link does not focus <main id=main>")

        # phone width: no horizontal scroll, navigation still reachable
        phone = browser.new_page(viewport={"width": 375, "height": 740})
        for path in ["/", "/scan", "/runs", run_url.replace(server.url, ""), "/label", "/benchmark"]:
            phone.goto(server.url + path)
            phone.wait_for_load_state("networkidle")
            if phone.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                bad.append(f"phone {path}: horizontal scroll")
        bad += audit(phone, "phone-benchmark")
        browser.close()
        assert not bad, "\n".join(bad)
