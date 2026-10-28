"""Playwright lifecycle, determinism and viewport tiling (guide section 6.2)."""
import os
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..detect import OCCLUSION_JS
from ..models import Capture, StateSpec, Tile
from ..store import ArtifactStore
from .axe import run_axe

HERE = Path(__file__).parent
SNAPSHOT_JS = (HERE / "snapshot.js").read_text()
PSEUDO_LOC_JS = (HERE / "pseudo_loc.js").read_text()

FREEZE_CSS = ("*,*::before,*::after{animation:none!important;transition:none!important;"
              "caret-color:transparent!important}html{scroll-behavior:auto!important}")


class Browsers:
    """Async context manager owning one Chromium. FIXEL_CHROMIUM_PATH points at a pre-installed binary."""

    async def __aenter__(self) -> Browser:
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(
            executable_path=os.environ.get("FIXEL_CHROMIUM_PATH") or None)
        return self.browser

    async def __aexit__(self, *exc):
        await self.browser.close()
        await self._pw.stop()


async def new_context(browser: Browser) -> BrowserContext:
    # scale 1 makes CSS px == screenshot px, so DOM rects can be sent to SAM unchanged
    return await browser.new_context(device_scale_factor=1, reduced_motion="reduce",
                                     locale="en-US", timezone_id="UTC")


def route_url(route: str) -> str:
    """'/checkout' -> '/checkout'; 'story:button--primary' -> Storybook's isolated iframe URL."""
    if route.startswith("story:"):
        return f"/iframe.html?id={route.removeprefix('story:')}&viewMode=story"
    return route


async def replay_step(page: Page, step: dict) -> None:
    raise NotImplementedError("explorer replay (guide section 8.2) is not built yet")


async def prepare(ctx: BrowserContext, base_url: str, s: StateSpec) -> Page:
    page = await ctx.new_page()
    await page.set_viewport_size({"width": s.width, "height": s.height})
    await page.emulate_media(color_scheme=s.theme)
    await page.goto(base_url.rstrip("/") + route_url(s.route), wait_until="networkidle")
    await page.add_style_tag(content=FREEZE_CSS)
    await page.evaluate("() => document.fonts.ready")
    if s.text_stress == "pseudo":
        await page.evaluate(PSEUDO_LOC_JS)              # lengthen and accent every text node
    for step in s.replay:
        await replay_step(page, step)                    # selector-based replay (section 8.2)
    return page


async def capture_page(page: Page, s: StateSpec, store: ArtifactStore, max_tiles: int = 6) -> Capture:
    """Tile an already prepared page the way a user scrolls: one viewport shot, snapshot and occlusion sample per tile."""
    doc_h = await page.evaluate("() => document.documentElement.scrollHeight")
    tiles, snap = [], None
    for y in range(0, min(max(doc_h, 1), s.height * max_tiles), s.height):
        await page.evaluate(f"window.scrollTo(0, {y})")
        png = await page.screenshot(animations="disabled")          # viewport only
        snap = await page.evaluate(SNAPSHOT_JS)
        occ = await page.evaluate(OCCLUSION_JS)
        tiles.append(Tile(scroll_y=y, png_sha=store.put(png), elements=snap["elements"], occlusion=occ))
    axe = await run_axe(page)
    return Capture(state=s, vw=snap["vw"], vh=snap["vh"], doc_w=snap["doc_w"], tiles=tiles, axe=axe)


async def capture(ctx: BrowserContext, base_url: str, s: StateSpec, store: ArtifactStore,
                  max_tiles: int = 6) -> tuple[Page, Capture]:
    """Returns the page still open: the opacity-diff check needs it; the caller closes it."""
    page = await prepare(ctx, base_url, s)
    return page, await capture_page(page, s, store, max_tiles)
