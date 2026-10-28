"""Geometry oracles: pure functions over a captured snapshot, no I/O (guide section 6.3).

Each per-tile oracle returns Candidates with state_key="" and tile=-1; run_oracles stamps them.
"""
from collections import defaultdict
from itertools import combinations

from ..models import Candidate, Capture, DefectType, Element, Tile


def area(r): return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])
def inter(a, b): return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
def box(e): return e.text_rect or e.rect
def is_content(e): return e.text_rect is not None or e.replaced or e.interactive


def cand(type_: DefectType, tile: Tile, elements: list[int], **metrics: float) -> Candidate:
    return Candidate(type=type_, state_key="", tile=-1, elements=elements, metrics=metrics)


def ancestors(e: Element, by_id: dict[int, Element]):
    p = e.parent
    while p is not None and p in by_id:
        yield p
        p = by_id[p].parent


def is_stacked(a: Element, b: Element, by_id: dict[int, Element]) -> bool:
    """True when either element is positioned out of normal flow, or sits inside a fixed or sticky ancestor
    (a sticky nav overlays whatever scrolls under it). A hint for triage, not a filter."""
    for e in (a, b):
        if e.style["position"] not in ("static", ""):
            return True
        if any(by_id[x].style["position"] in ("fixed", "sticky") for x in ancestors(e, by_id)):
            return True
    return False


def is_visual_container(p: Element) -> bool:
    bg = p.style["backgroundColor"]
    border = float(p.style["borderTopWidth"].removesuffix("px") or 0)
    return bg not in ("rgba(0, 0, 0, 0)", "transparent") or border > 0


def viewport_protrusion(cap: Capture, tile: Tile):
    if cap.doc_w <= cap.vw + 1:
        return []
    by_id = {e.id: e for e in tile.elements}
    scrollers = {e.id for e in tile.elements if e.style["overflowX"] in ("auto", "scroll")}
    over = [e for e in tile.elements if e.rect[2] > cap.vw + 1
            and not any(a in scrollers for a in ancestors(e, by_id))]   # inside a scroller is fine
    parents_of_over = {e.parent for e in over}
    # report the deepest culprits: protruding elements with no protruding child
    return [cand("viewport_protrusion", tile, [e.id], overflow_px=e.rect[2] - cap.vw)
            for e in over if e.id not in parents_of_over]


def collisions(tile: Tile, min_px: float = 24, cell: int = 64):
    by_id = {e.id: e for e in tile.elements}
    anc: dict[int, set[int]] = {}

    def ancs(e: Element) -> set[int]:
        if e.id not in anc:
            anc[e.id] = set(ancestors(e, by_id))
        return anc[e.id]

    grid = defaultdict(list)                             # 64 px buckets keep this near-linear
    for e in filter(is_content, tile.elements):
        x1, y1, x2, y2 = box(e)
        for gx in range(int(x1) // cell, int(x2) // cell + 1):
            for gy in range(int(y1) // cell, int(y2) // cell + 1):
                grid[gx, gy].append(e)
    seen, out = set(), []
    for bucket in grid.values():
        for a, b in combinations(bucket, 2):
            k = (min(a.id, b.id), max(a.id, b.id))
            if k in seen:
                continue
            seen.add(k)
            if a.id in ancs(b) or b.id in ancs(a):
                continue
            ov = area(inter(box(a), box(b)))
            if ov < min_px:
                continue
            out.append(cand("collision", tile, [a.id, b.id], overlap_px=ov,
                            overlap_frac=ov / min(area(box(a)), area(box(b))),
                            stacked=float(is_stacked(a, b, by_id))))   # a hint for triage, not a filter
    return out


def clipped_text(tile: Tile):
    out = []
    for e in tile.elements:
        if not e.text:
            continue
        sw, cw, sh, ch = e.scroll
        clip_x = e.style["overflowX"] in ("hidden", "clip") and sw > cw + 1
        clip_y = e.style["overflowY"] in ("hidden", "clip") and sh > ch + 1
        if (clip_x and e.style["textOverflow"] != "ellipsis") or clip_y:   # an ellipsis is deliberate
            out.append(cand("clipped_text", tile, [e.id], hidden_x=max(0, sw - cw), hidden_y=max(0, sh - ch)))
    return out


def element_protrusion(tile: Tile, tol: float = 2):
    by_id = {e.id: e for e in tile.elements}
    out = []
    for e in filter(is_content, tile.elements):
        p = by_id.get(e.parent)
        if not p or not is_visual_container(p) or p.style["overflowX"] != "visible":
            continue
        if e.style["position"] == "fixed":               # laid out against the viewport, not the parent
            continue
        b, pr = box(e), p.rect
        over = max(pr[0] - b[0], b[2] - pr[2], pr[1] - b[1], b[3] - pr[3])
        if over > tol:
            out.append(cand("element_protrusion", tile, [e.id, p.id], protrude_px=over))
    return out


def occlusions(tile: Tile, min_cover: float = 0.4):
    return [cand("occlusion", tile, [int(i)] + ([o["by"]] if o["by"] is not None else []), covered=o["covered"])
            for i, o in tile.occlusion.items() if o["covered"] >= min_cover]


def small_targets(tile: Tile, min_px: float = 24):
    # approximates WCAG 2.2 SC 2.5.8; inline links in running text and the spacing exception are not modelled
    by_id = {e.id: e for e in tile.elements}
    return [cand("small_target", tile, [e.id], w=e.rect[2] - e.rect[0], h=e.rect[3] - e.rect[1])
            for e in tile.elements if e.interactive
            and min(e.rect[2] - e.rect[0], e.rect[3] - e.rect[1]) < min_px
            and not (e.tag == "a" and by_id.get(e.parent) and by_id[e.parent].text)]


def contrast(cap: Capture):
    """axe-core color-contrast violations, mapped to the last tile's element ids."""
    last = len(cap.tiles) - 1
    return [Candidate(type="contrast", state_key=cap.state.key, tile=last, elements=[int(a["fixel"])],
                      metrics={}) for a in cap.axe if a.get("fixel") is not None]


def run_oracles(cap: Capture) -> list[Candidate]:
    """All geometry oracles over every tile, stamped with the state key and tile index."""
    out: list[Candidate] = []
    for i, tile in enumerate(cap.tiles):
        found = [*viewport_protrusion(cap, tile), *collisions(tile), *clipped_text(tile),
                 *element_protrusion(tile), *occlusions(tile), *small_targets(tile)]
        out += [c.model_copy(update={"state_key": cap.state.key, "tile": i}) for c in found]
    return out + contrast(cap)
