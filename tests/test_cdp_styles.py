import asyncio
from pathlib import Path

from fixel.capture.browser import SNAPSHOT_JS, Browsers, new_context
from fixel.localize.cdp_styles import abs_to_app_path, matched_rules, url_to_repo_path
from fixel.scan import serve_static


def test_url_to_repo_path():
    assert url_to_repo_path("http://localhost:5173/src/index.css?t=123") == "src/index.css"
    assert url_to_repo_path("data:text/css;base64,AAAA") is None
    assert abs_to_app_path("/work/app/src/a.css", Path("/work/app")) == "src/a.css"
    assert abs_to_app_path("/elsewhere/a.css", Path("/work/app")) == "elsewhere/a.css"


def test_matched_rules_find_the_stylesheet_and_selector_behind_an_element(tmp_path):
    (tmp_path / "card.css").write_text(".promo { width: 480px; background: #fde; }\np { margin: 0; }\n")
    (tmp_path / "index.html").write_text(
        '<link rel="stylesheet" href="/card.css"><style>.promo { padding: 12px; }</style>'
        '<div class="promo"><p>Hello</p></div>')
    server, url = serve_static(tmp_path)

    async def go():
        async with Browsers() as browser:
            page = await (await new_context(browser)).new_page()
            await page.goto(url + "/index.html")
            snap = await page.evaluate(SNAPSHOT_JS)                  # tags elements with data-fixel-id
            promo = next(e for e in snap["elements"] if e["tag"] == "div")
            return await matched_rules(page, promo["id"], tmp_path)

    try:
        rules = asyncio.run(go())
    finally:
        server.shutdown()
    files = {(r["selector"], r["file"]) for r in rules}
    assert (".promo", "card.css") in files                            # width: 480px lives in card.css
    assert (".promo", "index.html") in files                          # an inline <style> reports the page it is in
    assert any("width: 480px" in r["css"] for r in rules if r["file"] == "card.css")
    assert all(r["selector"] != "html" for r in rules)                # user-agent rules are skipped
