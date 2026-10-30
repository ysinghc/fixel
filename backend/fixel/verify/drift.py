"""Line remapping after a patch, element identity across scans, and layout drift (guide section 7.5).

A patch adds or removes lines, so every data-loc below it moves; before/after comparisons must remap first.
All deterministic code: the verifier never calls a model.
"""
import re
from dataclasses import dataclass, field

from ..detect.fuse import text_hash
from ..detect.oracles import on_screen
from ..models import Candidate, Capture

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
LOC = re.compile(r"^(.+):(\d+):(\d+)$")


@dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    mapping: dict[int, int] = field(default_factory=dict)      # old line -> new line, for lines present in both


def line_remap(diff: str) -> dict[str, list[Hunk]]:
    """file -> hunks with an exact old->new line map. Context lines map to themselves shifted; a removed line paired
    with an added one (an edited line) maps to its replacement; a removed line with no replacement is unmapped."""
    out: dict[str, list[Hunk]] = {}
    cur: str | None = None
    h: Hunk | None = None
    old_ln = new_ln = old_left = new_left = 0
    pending: list[int] = []
    for line in diff.splitlines():
        if h is not None and (old_left > 0 or new_left > 0) and line[:1] in ("+", "-", " ", "\\", ""):
            if line.startswith("+"):
                if pending:
                    h.mapping[pending.pop(0)] = new_ln
                new_ln += 1; new_left -= 1
            elif line.startswith("-"):
                pending.append(old_ln); old_ln += 1; old_left -= 1
            elif not line.startswith("\\"):
                pending.clear()
                h.mapping[old_ln] = new_ln
                old_ln += 1; new_ln += 1; old_left -= 1; new_left -= 1
            continue
        pending.clear()
        h = None
        if line.startswith("+++ b/"):
            cur = line[6:].strip()
            out.setdefault(cur, [])
        elif (m := HUNK.match(line)) and cur is not None:
            old_len = int(m[2]) if m[2] is not None else 1
            new_len = int(m[4]) if m[4] is not None else 1
            h = Hunk(int(m[1]), old_len, int(m[3]), new_len)
            out[cur].append(h)
            old_ln, new_ln, old_left, new_left = h.old_start, h.new_start, old_len, new_len
    return out


def map_line(hunks: list[Hunk], ln: int) -> int:
    """Where old line `ln` is after the patch."""
    delta = 0
    for h in sorted(hunks, key=lambda x: x.old_start):
        if ln < h.old_start:
            break
        if ln < h.old_start + h.old_len:
            return h.mapping.get(ln, h.new_start + min(ln - h.old_start, max(0, h.new_len - 1)))
        delta += h.new_len - h.old_len
    return ln + delta


def remap_loc(loc: str, remap: dict[str, list[Hunk]] | None) -> str:
    m = LOC.match(loc)
    if not m or not remap or m[1] not in remap:
        return loc
    return f"{m[1]}:{map_line(remap[m[1]], int(m[2]))}:{m[3]}"


def remap_key(key: str, remap: dict[str, list[Hunk]] | None) -> str:
    """Finding keys are `type|part|part`; remap the parts that are source locations."""
    kind, *parts = key.split("|")
    return "|".join([kind, *sorted(remap_loc(p, remap) for p in parts)])


# ----------------------------------------------------------------------------- element identity and drift
def identity_index(cap: Capture, remap: dict[str, list[Hunk]] | None) -> dict[tuple, tuple]:
    """(loc, tag, text hash, nth) -> rect in DOCUMENT coordinates, for every element of one capture.

    Identity comes from the first tile's element list (ids are stable across a state's tiles); the rect comes from
    the first tile in which the element is on screen, so fixed and sticky elements keep their tile-0 position."""
    if not cap.tiles:
        return {}
    first = cap.tiles[0]
    counts: dict[tuple, int] = {}
    out: dict[tuple, tuple] = {}
    for e in first.elements:
        base = (remap_loc(e.loc, remap) if e.loc else None, e.tag, text_hash(e.text))
        nth = counts[base] = counts.get(base, -1) + 1
        for tile in cap.tiles:
            t = next((x for x in tile.elements if x.id == e.id), None)
            if t is not None and on_screen(cap, t):
                out[(*base, nth)] = (t.rect[0], t.rect[1] + tile.scroll_y, t.rect[2], t.rect[3] + tile.scroll_y)
                break
    return out


def label(k: tuple) -> str:
    """How an element is named in reports and in the exclusion set: its source location, else tag#text-hash."""
    return k[0] or f"{k[1]}#{k[2]}"


def layout_drift(before: Capture, after: Capture, remap, exclude: set[str], tol: float = 2,
                 grow: set[str] = frozenset()) -> set[str]:
    """Elements outside the fixed container that moved sideways or changed size. Pure vertical shifts are allowed:
    fixing an overflow legitimately pushes content below it down. Ancestors of the fixed region (`grow`) may also
    change height, since their content grew, but must not move or widen sideways."""
    b = identity_index(before, remap)           # before: locs remapped to where the patch moved them
    a = identity_index(after, None)
    moved: set[str] = set()
    for k, rb in b.items():
        ra = a.get(k)
        if ra is None or label(k) in exclude:
            continue
        sideways = abs(ra[0] - rb[0]) > tol or abs((ra[2] - ra[0]) - (rb[2] - rb[0])) > tol
        taller = abs((ra[3] - ra[1]) - (rb[3] - rb[1])) > tol
        if sideways or (taller and label(k) not in grow):
            moved.add(label(k))
    return moved


def _tree(cap: Capture, cand: Candidate):
    tile = cap.tiles[cand.tile]
    by_id = {e.id: e for e in tile.elements}
    chains = []
    for i in cand.elements:
        chain, x = [], by_id.get(i)
        while x is not None:
            chain.append(x.id)
            x = by_id.get(x.parent) if x.parent is not None else None
        chains.append(chain)
    common = [i for i in chains[0] if all(i in c for c in chains[1:])] if chains else []
    if not common:
        return by_id, None
    anc = by_id[common[0]]
    root = by_id.get(anc.parent, anc) if anc.parent is not None else anc
    return by_id, root


def _name(e, remap) -> str:
    return remap_loc(e.loc, remap) if e.loc else f"{e.tag}#{text_hash(e.text)}"


def container_locs(cap: Capture, cand: Candidate, remap=None) -> set[str]:
    """Elements (by source location, else tag#text-hash) a fix may legitimately change: everything under the PARENT of
    the finding's nearest common ancestor (a fix often lands on the wrapper, e.g. a width on the box around the
    overflowing text). Changes elsewhere on the page are side effects."""
    by_id, root = _tree(cap, cand)
    if root is None:
        return set()
    children: dict[int, list[int]] = {}
    for e in cap.tiles[cand.tile].elements:
        if e.parent is not None:
            children.setdefault(e.parent, []).append(e.id)
    names, stack = set(), [root.id]
    while stack:
        e = by_id[stack.pop()]
        names.add(_name(e, remap))
        stack.extend(children.get(e.id, []))
    return names


def ancestor_locs(cap: Capture, cand: Candidate, remap=None) -> set[str]:
    """The chain from the container's parent up to the root: their height may grow when the fixed content does."""
    by_id, root = _tree(cap, cand)
    out, x = set(), by_id.get(root.parent) if root is not None and root.parent is not None else None
    while x is not None:
        out.add(_name(x, remap))
        x = by_id.get(x.parent) if x.parent is not None else None
    return out
