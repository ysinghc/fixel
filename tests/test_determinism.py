"""Spike 3 (guide section 13): the same state rendered twice must hash equal, or every threshold is poisoned."""
import asyncio
from pathlib import Path

import pytest

from fixel.capture.browser import Browsers, capture, new_context
from fixel.cli import serve_static
from fixel.models import StateSpec
from fixel.store import ArtifactStore

SITE = Path(__file__).parent / "fixtures" / "site"


async def render_twice(url, state, store):
    shas = []
    async with Browsers() as browser:
        for _ in range(2):                                   # two separate contexts: nothing is shared
            ctx = await new_context(browser)
            page, cap = await capture(ctx, url, state, store)
            await page.close()
            await ctx.close()
            shas.append([t.png_sha for t in cap.tiles])
    return shas


@pytest.mark.parametrize("route,theme,stress", [("/index.html", "light", "none"), ("/index.html", "dark", "pseudo"),
                                                 ("/checkout.html", "light", "none")])
async def test_same_state_renders_identically(tmp_path, route, theme, stress):
    server, url = serve_static(SITE)
    try:
        a, b = await render_twice(url, StateSpec(route=route, width=375, height=600, theme=theme, text_stress=stress),
                                  ArtifactStore(tmp_path))
    finally:
        server.shutdown()
    assert a == b
