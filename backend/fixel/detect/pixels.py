"""Pixel evidence: the deterministic opacity diff now, SAM 3.1 box prompts next (guide section 6.4).

The opacity diff hides one element and counts how many pixels change inside a region. It is model-free,
so the verifier can use it. Extensions beyond the guide's snippet:
  * collisions are tested both ways (hide A, hide B), because either may be painted on top;
  * element protrusion measures paint in the part of the child outside its parent, since there is no overlap.
"""
import io

import numpy as np
from PIL import Image

from ..models import Candidate, Capture, Element, PixelEvidence
from .fuse import observable
from .oracles import box, inter

HIDE_JS = ("([s, hide]) => { const e = document.querySelector(s); if (!e) return null; const p = e.style.opacity;"
           " if (hide) { e.style.setProperty('opacity', '0', 'important'); return p; }"
           " e.style.opacity = p; return p; }")
PIXEL_TOL = 24                                # summed RGB difference that counts as a changed pixel


def to_np(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))


def outside(inner, outer) -> list[tuple]:
    """Up to four strips covering the part of `inner` that lies outside `outer`."""
    x1, y1, x2, y2 = inner
    ox1, oy1, ox2, oy2 = outer
    strips = [(x1, y1, min(x2, ox1), y2), (max(x1, ox2), y1, x2, y2),
              (max(x1, ox1), y1, min(x2, ox2), min(y2, oy1)), (max(x1, ox1), max(y1, oy2), min(x2, ox2), y2)]
    return [s for s in strips if s[2] > s[0] and s[3] > s[1]]


async def hidden_diff(page, scroll_y: int, hide_id: int, rects: list[tuple]) -> float:
    """Share of pixels inside `rects` that change when element `hide_id` is made transparent."""
    if not rects:
        return 0.0
    await page.evaluate(f"window.scrollTo(0, {scroll_y})")
    sel = f'[data-fixel-id="{hide_id}"]'
    before = to_np(await page.screenshot(animations="disabled"))
    prev = await page.evaluate(HIDE_JS, [sel, True])
    if prev is None:
        return 0.0
    try:
        after = to_np(await page.screenshot(animations="disabled"))
    finally:
        await page.evaluate("([s, p]) => { document.querySelector(s).style.opacity = p; }", [sel, prev])
    h, w = before.shape[:2]
    mask = np.zeros((h, w), bool)
    for x1, y1, x2, y2 in rects:
        mask[max(0, int(y1)):min(h, int(y2)), max(0, int(x1)):min(w, int(x2))] = True
    if not mask.any():
        return 0.0
    changed = np.abs(before.astype(int) - after.astype(int)).sum(axis=2) > PIXEL_TOL
    return float(changed[mask].mean())


async def opacity_diff(page, scroll_y: int, a: Element, b: Element, full_boxes: bool = False) -> float:
    """Share of A∩B pixels that change when B is made transparent; > 0 means B visibly covers A.

    Boxes are the tight text boxes by default (right for text-on-text collisions). Occlusion passes
    full_boxes=True: a banner covers a button through its whole rectangle, not just where its words sit.
    """
    r = inter(a.rect, b.rect) if full_boxes else inter(box(a), box(b))
    return await hidden_diff(page, scroll_y, b.id, [r] if r[2] > r[0] and r[3] > r[1] else [])


async def pixel_evidence(page, cap: Capture, c: Candidate) -> PixelEvidence:
    """Evidence for one candidate. The page must be the one captured for `cap`, still open."""
    tile = cap.tiles[c.tile]
    by_id = {e.id: e for e in tile.elements}
    els = [by_id[i] for i in c.elements if i in by_id]
    diff = None
    if c.type == "collision" and len(els) == 2:
        a, b = els
        diff = max(await opacity_diff(page, tile.scroll_y, a, b), await opacity_diff(page, tile.scroll_y, b, a))
    elif c.type == "occlusion" and len(els) == 2:
        diff = await opacity_diff(page, tile.scroll_y, els[0], els[1], full_boxes=True)   # els[1] covers
    elif c.type == "element_protrusion" and len(els) == 2:
        child, parent = els
        diff = await hidden_diff(page, tile.scroll_y, child.id, outside(box(child), parent.rect))
    px = PixelEvidence(opacity_diff=diff, observable=False)
    return px.model_copy(update={"observable": observable(c, px)})
