import asyncio
import os
from pathlib import Path

import pytest

from fixel.capture.browser import FREEZE_CSS, Browsers, capture_page, new_context
from fixel.detect.oracles import run_oracles
from fixel.models import Capture, StateSpec
from fixel.store import ArtifactStore

# Use the pre-installed Chromium when Playwright's own browser download is absent.
if "FIXEL_CHROMIUM_PATH" not in os.environ and Path("/opt/pw-browsers/chromium").exists():
    os.environ["FIXEL_CHROMIUM_PATH"] = "/opt/pw-browsers/chromium"


@pytest.fixture
def snap(tmp_path):
    """snap(html, width=375, height=600) -> Capture of the page, rendered from a string."""
    store = ArtifactStore(tmp_path / "artifacts")

    def run(html: str, width: int = 375, height: int = 600, theme: str = "light") -> Capture:
        async def go():
            async with Browsers() as browser:
                ctx = await new_context(browser)
                page = await ctx.new_page()
                await page.set_viewport_size({"width": width, "height": height})
                await page.emulate_media(color_scheme=theme)
                await page.set_content(html)
                await page.add_style_tag(content=FREEZE_CSS)
                return await capture_page(page, StateSpec(route="/t", width=width, height=height, theme=theme), store)
        return asyncio.run(go())
    return run


@pytest.fixture
def found(snap):
    """found(html, **kw) -> list of candidate types, via the full oracle runner."""
    def run(html: str, **kw):
        return run_oracles(snap(html, **kw))
    return run
