"""Pixel evidence: the deterministic opacity diff now, SAM 3.1 box prompts next (guide section 6.4).

The opacity diff hides one element and counts how many pixels change inside a region. It is model-free,
so the verifier can use it. Extensions beyond the guide's snippet:
  * a collision is observable only when *both* elements paint in the overlap (each is probed with the other hidden), so a
    visible line overlapped by invisible text is not a collision, whichever of the two is on top;
  * element protrusion measures paint in the part of the child outside its parent, since there is no overlap.
"""
import io
from collections import defaultdict

import numpy as np
from PIL import Image

from ..meta.sam import clamp_box, iou_and_spill, segment_boxes
from ..models import Candidate, Capture, Element, PixelEvidence
from ..store import ArtifactStore
from .fuse import observable
from .oracles import box, inter

HIDE_JS = ("([s, hide]) => { const e = document.querySelector(s); if (!e) return null; const p = e.style.opacity;"
           " if (hide) { e.style.setProperty('opacity', '0', 'important'); return p; }"
           " e.style.opacity = p; return p; }")
# the element may be gone by now (a live-updating page re-rendered it): restoring must not throw
RESTORE_JS = "([s, p]) => { const e = document.querySelector(s); if (e) e.style.opacity = p; }"
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
        await page.evaluate(RESTORE_JS, [sel, prev])
    h, w = before.shape[:2]
    mask = np.zeros((h, w), bool)
    for x1, y1, x2, y2 in rects:
        mask[max(0, int(y1)):min(h, int(y2)), max(0, int(x1)):min(w, int(x2))] = True
    if not mask.any():
        return 0.0
    changed = np.abs(before.astype(int) - after.astype(int)).sum(axis=2) > PIXEL_TOL
    return float(changed[mask].mean())


async def paints_alone(page, scroll_y: int, hide_id: int, probe_id: int, rects: list[tuple]) -> float:
    """Share of pixels in `rects` that change when `probe_id` is hidden while `hide_id` is already hidden:
    does the probe paint there on its own?"""
    sel = f'[data-fixel-id="{hide_id}"]'
    prev = await page.evaluate(HIDE_JS, [sel, True])
    if prev is None:
        return 0.0
    try:
        return await hidden_diff(page, scroll_y, probe_id, rects)
    finally:
        await page.evaluate(RESTORE_JS, [sel, prev])


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
        r = inter(box(a), box(b))
        rects = [r] if r[2] > r[0] and r[3] > r[1] else []
        diff = min(await paints_alone(page, tile.scroll_y, a.id, b.id, rects), await paints_alone(page, tile.scroll_y, b.id, a.id, rects))
    elif c.type == "occlusion" and len(els) == 2:
        diff = await opacity_diff(page, tile.scroll_y, els[0], els[1], full_boxes=True)   # els[1] covers
    elif c.type == "element_protrusion" and len(els) == 2:
        child, parent = els
        diff = await hidden_diff(page, tile.scroll_y, child.id, outside(box(child), parent.rect))
    px = PixelEvidence(opacity_diff=diff, observable=False)
    return px.model_copy(update={"observable": observable(c, px)})


SAM_TYPES = {"occlusion", "collision", "element_protrusion"}


def sam_rects(cap: Capture, c: Candidate) -> dict[int, tuple]:
    """Element id -> the rectangle SAM is asked about: the covered target, both colliding texts, or the protruding child."""
    by_id = {e.id: e for e in cap.tiles[c.tile].elements}
    els = [by_id[i] for i in c.elements if i in by_id]
    if c.type == "occlusion" and els:
        return {els[0].id: els[0].rect}
    if c.type == "collision":
        return {e.id: box(e) for e in els}
    if c.type == "element_protrusion" and els:
        return {els[0].id: box(els[0])}
    return {}


async def add_sam(cap: Capture, cands: list[Candidate], evidence: list[PixelEvidence], store: ArtifactStore,
                  emit=None) -> list[PixelEvidence]:
    """Ask SAM 3.1 what is painted in each candidate's DOM boxes (one request per tile, 16 objects per request)
    and fold its confidence and returned bounds into the evidence. Raises if the model cannot be called."""
    size = (cap.vw, cap.vh)                       # scale 1: CSS px == image px
    per_tile: dict[int, dict[int, tuple]] = defaultdict(dict)
    for c in cands:
        for i, r in sam_rects(cap, c).items():
            if (b := clamp_box(r, size)):
                per_tile[c.tile][i] = b
    got = {t: await segment_boxes(store.get(cap.tiles[t].png_sha), cap.tiles[t].png_sha, size, boxes, emit)
           for t, boxes in per_tile.items()}
    out = []
    for c, px in zip(cands, evidence):
        pairs = [(got[c.tile][i], per_tile[c.tile][i]) for i in sam_rects(cap, c)
                 if i in per_tile.get(c.tile, {}) and i in got.get(c.tile, {}) and got[c.tile][i].conf is not None]
        if not pairs:
            out.append(px)
            continue
        m = [iou_and_spill(b, g) for g, b in pairs]
        px = px.model_copy(update={"sam_conf": min(g.conf for g, _ in pairs), "sam_iou": min(i for i, _ in m),
                                   "sam_spill": max(s for _, s in m),
                                   "sam_boxes": [(g.left, g.top, g.right, g.bottom, g.conf) for g, _ in pairs]})
        out.append(px.model_copy(update={"observable": observable(c, px)}))
    return out
