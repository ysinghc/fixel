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


def pinned_root(e: Element, by_id: dict[int, Element]) -> Element | None:
    """The element itself or the nearest ancestor that is position: fixed or sticky (stays put while scrolling)."""
    for x in (e, *(by_id[a] for a in ancestors(e, by_id))):
        if x.style["position"] in ("fixed", "sticky"):
            return x
    return None


def scrolls_clear(cap: Capture, tile: Tile, flow: Element, pinned: Element) -> bool:
    """Can the user scroll so `flow` is on screen and not under `pinned`? Vertical scroll only moves `flow`, so it is
    enough to test the scroll positions where an edge of `flow` meets an edge of `pinned`, plus the two ends."""
    max_scroll = max(0, cap.doc_h - cap.vh)
    top, bottom = flow.rect[1] + tile.scroll_y, flow.rect[3] + tile.scroll_y        # document coordinates
    p_top, p_bottom = pinned.rect[1], pinned.rect[3]                                # fixed in the viewport
    edges = {0, max_scroll, bottom - p_top, top - p_bottom}
    for sy in {min(max_scroll, max(0, round(e + d))) for e in edges for d in (-1, 0, 1)}:
        v_top, v_bottom = top - sy, bottom - sy
        if v_bottom > 0 and v_top < cap.vh and (v_bottom <= p_top or v_top >= p_bottom):
            return True
    return False


def is_transient(cap: Capture, tile: Tile, c: Candidate) -> bool:
    """A collision or occlusion between a fixed/sticky element and in-flow content that the user can scroll apart
    (a sticky nav over content scrolled under it) is by design. One that cannot be scrolled clear (a cookie banner
    over the last button) is not."""
    if c.type not in ("collision", "occlusion") or cap.doc_h <= 0:
        return False
    by_id = {e.id: e for e in tile.elements}
    els = [by_id[i] for i in c.elements if i in by_id]
    if len(els) != 2:
        return False
    roots = [pinned_root(e, by_id) for e in els]
    if (roots[0] is None) == (roots[1] is None):
        return False                                        # both pinned or neither: scrolling does not separate them
    pinned, flow = (roots[0], els[1]) if roots[0] else (roots[1], els[0])
    return scrolls_clear(cap, tile, flow, pinned)


def is_visual_container(p: Element) -> bool:
    bg = p.style["backgroundColor"]
    border = float(p.style["borderTopWidth"].removesuffix("px") or 0)
    return bg not in ("rgba(0, 0, 0, 0)", "transparent") or border > 0


def viewport_protrusion(cap: Capture, tile: Tile):
    scrolls = cap.doc_w > cap.vw + 1
    if not scrolls and not cap.root_clip:
        return []
    by_id = {e.id: e for e in tile.elements}
    scrollers = {e.id for e in tile.elements if e.style["overflowX"] in ("auto", "scroll")}

    def right(e: Element) -> float:                      # text spilling out of a narrow box counts, not only the box
        return max(e.rect[2], e.text_rect[2]) if e.text_rect else e.rect[2]

    if scrolls:
        over = [e for e in tile.elements if right(e) > cap.vw + 1
                and not any(a in scrollers for a in ancestors(e, by_id))]   # inside a scroller is fine
    else:
        # The page cannot scroll sideways because the root clips overflow, so overflow is simply cut off. Decorative blobs
        # hang off the edge on purpose, so only text and controls that *start* on screen and run off it count, and
        # nothing inside a container that clips or scrolls (carousels) or that sits entirely off screen (a closed drawer).
        scrollers |= {e.id for e in tile.elements if e.tag != "body" and e.style["overflowX"] in ("hidden", "clip")}
        over = [e for e in tile.elements if (e.text_rect or e.interactive) and e.rect[0] < cap.vw - 1 and right(e) > cap.vw + 1
                and not any(a in scrollers for a in ancestors(e, by_id))]
    parents_of_over = {e.parent for e in over}
    over_ids = {e.id for e in over}
    # report the deepest culprits: protruding elements with no protruding child ...
    deepest = [e for e in over if e.id not in parents_of_over]
    by_parent: dict[int | None, list[Element]] = defaultdict(list)
    for e in deepest:
        by_parent[e.parent].append(e)
    culprits: list[Element] = []
    for pid, group in by_parent.items():
        # ... but when several siblings protrude because their parent does, the parent is the one thing to fix
        culprits += [by_id[pid]] if len(group) >= 2 and pid in over_ids else group
    extra = {} if scrolls else {"clipped_by_root": 1.0}
    return [cand("viewport_protrusion", tile, [e.id], overflow_px=right(e) - cap.vw, **extra) for e in culprits]


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
    """Covered interactive elements. The coverer is named by its fixed/sticky root when it has one (the whole banner),
    not by whichever inner element one of the five sample points happened to hit, so the finding key is stable."""
    by_id = {e.id: e for e in tile.elements}
    out = []
    for i, o in tile.occlusion.items():
        if o["covered"] < min_cover:
            continue
        ids = [int(i)]
        if o["by"] is not None:
            hit = by_id.get(o["by"])
            root = pinned_root(hit, by_id) if hit else None
            ids.append(root.id if root else o["by"])
        out.append(cand("occlusion", tile, ids, covered=o["covered"]))
    return out


def drop_explained_collisions(tile: Tile, found: list[Candidate]) -> list[Candidate]:
    """A collision between a covered element and something inside its occluder is the same defect as the occlusion:
    report it once. (Otherwise one defect has two keys, and a small layout shift can make the second look new.)"""
    occ = [c for c in found if c.type == "occlusion" and len(c.elements) == 2]
    if not occ:
        return found
    children: dict[int, list[int]] = defaultdict(list)
    for e in tile.elements:
        if e.parent is not None:
            children[e.parent].append(e.id)

    def subtree(root: int) -> set[int]:
        out, stack = set(), [root]
        while stack:
            x = stack.pop()
            out.add(x)
            stack += children.get(x, [])
        return out

    covered = [(o.elements[0], subtree(o.elements[1])) for o in occ]
    return [c for c in found if not (c.type == "collision" and any(
        (a in c.elements and (set(c.elements) - {a}) <= inside) for a, inside in covered))]


def small_targets(tile: Tile, min_px: float = 24):
    # approximates WCAG 2.2 SC 2.5.8; inline links in running text and the spacing exception are not modelled
    by_id = {e.id: e for e in tile.elements}
    return [cand("small_target", tile, [e.id], w=e.rect[2] - e.rect[0], h=e.rect[3] - e.rect[1])
            for e in tile.elements if e.interactive
            and min(e.rect[2] - e.rect[0], e.rect[3] - e.rect[1]) < min_px
            and not (e.tag == "a" and by_id.get(e.parent) and by_id[e.parent].text)]


def on_screen(cap: Capture, e: Element) -> bool:
    """Any part of the element lies inside the viewport shot (the snapshot also lists everything off-screen)."""
    return e.rect[2] > 0 and e.rect[0] < cap.vw and e.rect[3] > 0 and e.rect[1] < cap.vh


def contrast(cap: Capture):
    """axe-core color-contrast violations, placed in the first tile where the element is on screen."""
    out = []
    for a in cap.axe:
        if a.get("fixel") is None:
            continue
        i = int(a["fixel"])
        for t, tile in enumerate(cap.tiles):
            e = next((x for x in tile.elements if x.id == i), None)
            if e and on_screen(cap, e):
                out.append(Candidate(type="contrast", state_key=cap.state.key, tile=t, elements=[i], metrics={}))
                break
    return out


def run_oracles(cap: Capture) -> list[Candidate]:
    """All geometry oracles over every tile, stamped with the state key and tile index. A candidate is kept only in
    tiles where all its elements are on screen, so a long page does not report (or triage) the same thing off-screen."""
    out: list[Candidate] = []
    for i, tile in enumerate(cap.tiles):
        by_id = {e.id: e for e in tile.elements}
        found = drop_explained_collisions(tile, [*viewport_protrusion(cap, tile), *collisions(tile), *clipped_text(tile),
                                                 *element_protrusion(tile), *occlusions(tile), *small_targets(tile)])
        for c in found:
            if not all(on_screen(cap, by_id[x]) for x in c.elements if x in by_id):
                continue
            c = c.model_copy(update={"state_key": cap.state.key, "tile": i})
            if is_transient(cap, tile, c):
                c.metrics["transient"] = 1.0                # fuse() dismisses these in code, no model call spent
            out.append(c)
    return out + contrast(cap)
