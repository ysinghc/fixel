"""Defect injection operators and the three controls (guide section 9.2).

Any rendered page becomes a test case by injecting a known defect into one element. The injection runs in the page (see
inject.js); the target is chosen from the snapshot of the unmutated state, so a case always names the element it broke.
`hits` lists the defect types that count as detecting the mutation. Controls have a known answer without geometry:
`badge_overlap` and `open_dropdown` must be dismissed, `invisible_overlap` must be not observable.
"""
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..models import Capture, Element

INJECT_JS = (Path(__file__).parent / "inject.js").read_text()
TEXT_TAGS = {"p", "span", "h1", "h2", "h3", "h4", "h5", "h6", "a", "li", "div", "label", "button", "td", "small", "strong", "em"}


@dataclass(frozen=True)
class Ctx:
    """What a precondition may look at: the other elements of the same tile and the viewport."""
    els: tuple[Element, ...]
    vw: int
    vh: int

    def children(self, e: Element) -> list[Element]:
        return [c for c in self.els if c.parent == e.id]

    def earlier_siblings(self, e: Element) -> list[Element]:
        return [c for c in self.els if c.parent == e.parent and c.id < e.id]


@dataclass(frozen=True)
class Mutation:
    name: str
    hits: frozenset[str]                         # defect types that count as detecting it
    applies: Callable[[Element, Ctx], bool]      # precondition on the target element
    control: str | None = None                   # "dismissed" or "not_observable" for control cases
    note: str = ""                               # what it tests


def w(e: Element) -> float:
    return e.rect[2] - e.rect[0]


def h(e: Element) -> float:
    return e.rect[3] - e.rect[1]


def font(e: Element) -> float:
    try:
        return float(e.style.get("fontSize", "16px").removesuffix("px"))
    except ValueError:
        return 16.0


def is_text(e: Element) -> bool:
    return bool(e.text.strip()) and not e.replaced and e.tag in TEXT_TAGS and h(e) > 0


def has_neighbour_right(e: Element, c: Ctx) -> bool:
    return any(o.id != e.id and o.text.strip() and o.parent != e.id and e.parent != o.id
               and 0 <= o.rect[0] - e.rect[2] < 40 and min(h(e), h(o)) > 0
               and (min(e.rect[3], o.rect[3]) - max(e.rect[1], o.rect[1])) > 0.5 * min(h(e), h(o)) for o in c.els)


def wrapped_row(e: Element, c: Ctx) -> bool:
    kids = c.children(e)
    return (e.style.get("display") == "flex" and e.style.get("flexWrap") == "wrap" and e.style.get("flexDirection", "row") == "row"
            and len(kids) >= 3 and sum(w(k) for k in kids) > w(e) * 1.05)


def near_bottom(e: Element, c: Ctx) -> bool:
    return e.interactive and e.rect[1] >= c.vh - 120 and e.rect[3] <= c.vh


OPS = [
    # Operators that push text over its neighbours also count `occlusion`: the oracles report an interactive element
    # overlapped by another as occlusion, and it is the same defect. The report also gives a looser "involves the target" rate.
    Mutation("nowrap_long", frozenset({"viewport_protrusion", "element_protrusion", "clipped_text", "occlusion"}),
             lambda e, c: is_text(e) and not c.children(e) and e.rect[0] >= 0, note="geometry"),
    Mutation("fixed_width", frozenset({"viewport_protrusion"}),
             lambda e, c: e.style.get("display") in ("block", "flex", "grid") and not e.replaced and w(e) >= 80
             and e.rect[0] + 480 > c.vw + 8, note="geometry"),
    Mutation("clamp_height", frozenset({"clipped_text"}),
             lambda e, c: is_text(e) and len(e.text) >= 50 and h(e) >= 2.2 * font(e), note="geometry"),
    Mutation("negative_margin", frozenset({"collision", "occlusion"}),
             lambda e, c: is_text(e) and bool(c.earlier_siblings(e)), note="geometry + opacity diff"),
    Mutation("nudge", frozenset({"collision", "occlusion", "viewport_protrusion", "element_protrusion"}),
             lambda e, c: is_text(e) and not c.children(e) and has_neighbour_right(e, c), note="geometry + opacity diff"),
    Mutation("font_bump", frozenset({"clipped_text", "element_protrusion", "viewport_protrusion", "collision"}),   # spilled text may land on a neighbour
             lambda e, c: e.interactive and not e.replaced and w(e) >= 40 and e.text_rect is not None
             and (e.text_rect[2] - e.text_rect[0]) * 1.6 > w(e), note="geometry"),     # the bumped text must not fit
    Mutation("no_wrap_row", frozenset({"viewport_protrusion", "element_protrusion"}), wrapped_row, note="geometry"),
    Mutation("img_unbounded", frozenset({"viewport_protrusion"}),
             lambda e, c: e.tag == "img" and e.rect[0] + 900 > c.vw + 8, note="geometry"),
    Mutation("low_contrast", frozenset({"contrast"}), lambda e, c: is_text(e) and not c.children(e), note="axe-core"),
    Mutation("tiny_target", frozenset({"small_target"}),
             lambda e, c: e.interactive and w(e) > 20 and h(e) > 20, note="geometry"),
    Mutation("opaque_banner", frozenset({"occlusion"}), near_bottom, note="hit testing + pixels"),
    Mutation("ghost_banner", frozenset({"occlusion"}), near_bottom,
             note="pixels only: hit testing is blind to it, so this measures a known gap"),
    Mutation("badge_overlap", frozenset(), lambda e, c: e.interactive and w(e) >= 24 and h(e) >= 20,
             control="dismissed", note="control: Spark must dismiss it"),
    Mutation("open_dropdown", frozenset(), lambda e, c: e.interactive and w(e) >= 24 and h(e) >= 20,
             control="dismissed", note="control: Spark must dismiss it"),
    Mutation("invisible_overlap", frozenset(), lambda e, c: is_text(e) and not c.children(e),
             control="not_observable", note="control: nothing painted, so not observable"),
]
BY_NAME = {m.name: m for m in OPS}


def targets_for(op: Mutation, cap: Capture, tile: int) -> list[Element]:
    """Elements of one tile that this operator can break; each must have a source location so a case can be localized."""
    t = cap.tiles[tile]
    ctx = Ctx(tuple(t.elements), cap.vw, cap.vh)
    return [e for e in t.elements if e.loc and op.applies(e, ctx)]


def pick(cap: Capture, op: Mutation, rng: random.Random) -> tuple[int, Element] | None:
    """A (tile, element) this operator applies to, or None. A seeded rng makes the choice reproducible."""
    tiles = list(range(len(cap.tiles)))
    rng.shuffle(tiles)
    for t in tiles:
        cands = targets_for(op, cap, t)
        if cands:
            return t, rng.choice(cands)
    return None


async def inject(page, op: Mutation, target_id: int) -> bool:
    """Apply the mutation to the element the last snapshot tagged data-fixel-id=target_id."""
    return bool(await page.evaluate(INJECT_JS, [target_id, op.name]))
