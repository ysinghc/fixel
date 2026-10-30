"""Line remap, element identity and layout drift. Wrong remaps make the verifier report false new findings (guide 14.1)."""
from fixel.models import Candidate, Capture, Element, StateSpec, Tile
from fixel.verify.drift import (ancestor_locs, container_locs, identity_index, layout_drift, line_remap, map_line, remap_key,
                                remap_loc)

# 7 lines of context around line 20; line 20 is replaced by two lines (net +1)
GROW = """diff --git a/src/A.jsx b/src/A.jsx
--- a/src/A.jsx
+++ b/src/A.jsx
@@ -17,7 +17,8 @@
 l17
 l18
 l19
-l20
+l20 edited
+l20 extra line
 l21
 l22
 l23
"""
SHRINK = """diff --git a/src/A.jsx b/src/A.jsx
--- a/src/A.jsx
+++ b/src/A.jsx
@@ -10,5 +10,3 @@
 l10
-l11
-l12
 l13
 l14
"""


def test_lines_above_a_hunk_do_not_move():
    r = line_remap(GROW)["src/A.jsx"]
    assert [map_line(r, n) for n in (1, 10, 16)] == [1, 10, 16]


def test_lines_below_a_hunk_shift_by_its_net_delta():
    r = line_remap(GROW)["src/A.jsx"]
    assert [map_line(r, n) for n in (24, 100)] == [25, 101]


def test_context_lines_inside_the_hunk_after_the_change_shift_too():
    # the case the guide's remap misses: l21-l23 are inside the hunk, below the inserted line
    r = line_remap(GROW)["src/A.jsx"]
    assert [map_line(r, n) for n in (17, 18, 19, 21, 22, 23)] == [17, 18, 19, 22, 23, 24]


def test_an_edited_line_maps_to_its_replacement():
    assert map_line(line_remap(GROW)["src/A.jsx"], 20) == 20


def test_removed_lines_and_lines_after_a_shrinking_hunk():
    r = line_remap(SHRINK)["src/A.jsx"]
    assert map_line(r, 13) == 11 and map_line(r, 14) == 12 and map_line(r, 15) == 13


def test_two_hunks_accumulate():
    d = GROW + SHRINK.replace("diff --git a/src/A.jsx b/src/A.jsx\n--- a/src/A.jsx\n+++ b/src/A.jsx\n", "").replace("@@ -10,5 +10,3 @@", "@@ -40,5 +41,3 @@")
    r = line_remap(d)["src/A.jsx"]
    assert map_line(r, 30) == 31 and map_line(r, 60) == 59           # +1 from the first hunk, then -2 from the second


def test_remap_loc_and_key():
    r = line_remap(GROW)
    assert remap_loc("src/A.jsx:30:7", r) == "src/A.jsx:31:7"
    assert remap_loc("src/B.jsx:30:7", r) == "src/B.jsx:30:7"             # other files untouched
    assert remap_loc("p#abc123", r) == "p#abc123"                          # fingerprint keys have no line
    assert remap_key("collision|src/A.jsx:30:7|p#abc", r) == "collision|p#abc|src/A.jsx:31:7"
    assert remap_key("viewport_protrusion|src/A.jsx:5:1", None) == "viewport_protrusion|src/A.jsx:5:1"


def test_no_hunks_no_change():
    assert line_remap("") == {} and remap_loc("src/A.jsx:3:1", {}) == "src/A.jsx:3:1"


# ----------------------------------------------------------------------------- drift
def el(id_, rect, loc=None, tag="div", text="", parent=None, position="static"):
    return Element(id=id_, parent=parent, tag=tag, loc=loc, rect=rect, text_rect=None, text=text, interactive=False,
                   replaced=False, style={"position": position}, scroll=(0, 0, 0, 0))


def cap(elements, scroll_y=0, vw=400, vh=800):
    return Capture(state=StateSpec(route="/", width=vw), vw=vw, vh=vh, doc_w=vw, doc_h=2000,
                   tiles=[Tile(scroll_y=scroll_y, png_sha="x", elements=elements, occlusion={})], axe=[])


BEFORE = [el(0, (0, 0, 400, 600), "src/A.jsx:1:1"),
          el(1, (10, 100, 390, 140), "src/A.jsx:30:7", "p", "Hello"),
          el(2, (10, 200, 200, 240), "src/B.jsx:5:3", "button", "Pay")]


def test_vertical_shifts_are_allowed():
    after = [el(0, (0, 0, 400, 700), "src/A.jsx:1:1"), el(1, (10, 160, 390, 200), "src/A.jsx:31:7", "p", "Hello"),
             el(2, (10, 260, 200, 300), "src/B.jsx:5:3", "button", "Pay")]
    assert layout_drift(cap(BEFORE), cap(after), line_remap(GROW), set()) == {"src/A.jsx:1:1"}   # only the body grew
    after[0] = el(0, (0, 0, 400, 600), "src/A.jsx:1:1")
    assert layout_drift(cap(BEFORE), cap(after), line_remap(GROW), set()) == set()


def test_sideways_moves_and_size_changes_are_drift():
    wider = [BEFORE[0], BEFORE[1], el(2, (10, 200, 260, 240), "src/B.jsx:5:3", "button", "Pay")]
    assert layout_drift(cap(BEFORE), cap(wider), None, set()) == {"src/B.jsx:5:3"}
    moved = [BEFORE[0], BEFORE[1], el(2, (40, 200, 230, 240), "src/B.jsx:5:3", "button", "Pay")]
    assert layout_drift(cap(BEFORE), cap(moved), None, set()) == {"src/B.jsx:5:3"}
    taller = [BEFORE[0], BEFORE[1], el(2, (10, 200, 200, 280), "src/B.jsx:5:3", "button", "Pay")]
    assert layout_drift(cap(BEFORE), cap(taller), None, set()) == {"src/B.jsx:5:3"}


def test_changes_inside_the_fix_container_are_excluded_and_small_jitter_ignored():
    wider = [BEFORE[0], BEFORE[1], el(2, (10, 200, 260, 240), "src/B.jsx:5:3", "button", "Pay")]
    assert layout_drift(cap(BEFORE), cap(wider), None, {"src/B.jsx:5:3"}) == set()
    jitter = [BEFORE[0], BEFORE[1], el(2, (11, 200, 201, 241), "src/B.jsx:5:3", "button", "Pay")]
    assert layout_drift(cap(BEFORE), cap(jitter), None, set()) == set()


def test_elements_are_matched_by_remapped_loc_not_by_position_in_the_list():
    # the patch inserted a line above src/A.jsx:30, so the same element now reports :31 (and a new element appears first)
    after = [el(9, (0, 900, 10, 910), "src/New.jsx:1:1", "i")] + [
        el(0, (0, 0, 400, 600), "src/A.jsx:1:1"), el(1, (10, 100, 390, 140), "src/A.jsx:31:7", "p", "Hello"),
        el(2, (10, 200, 200, 240), "src/B.jsx:5:3", "button", "Pay")]
    assert layout_drift(cap(BEFORE), cap(after), line_remap(GROW), set()) == set()


def test_identity_uses_document_coordinates_across_tiles():
    c = Capture(state=StateSpec(route="/", width=400), vw=400, vh=300, doc_w=400, doc_h=900, axe=[], tiles=[
        Tile(scroll_y=0, png_sha="a", occlusion={}, elements=[el(0, (0, 0, 400, 200), "a:1:1"), el(1, (0, 500, 100, 540), "a:9:1", "p", "x")]),
        Tile(scroll_y=300, png_sha="b", occlusion={}, elements=[el(0, (0, -300, 400, -100), "a:1:1"), el(1, (0, 200, 100, 240), "a:9:1", "p", "x")])])
    idx = identity_index(c, None)
    assert idx[("a:9:1", "p", idx and next(k for k in idx if k[0] == "a:9:1")[2], 0)] == (0, 500, 100, 540)   # seen in tile 1, y + scroll 300


def test_duplicate_elements_get_distinct_nth_indices():
    rows = [el(0, (0, 0, 400, 600), "a:1:1"), el(1, (0, 10, 100, 30), "a:5:1", "li", "Row"), el(2, (0, 40, 100, 60), "a:5:1", "li", "Row")]
    keys = [k for k in identity_index(cap(rows), None) if k[0] == "a:5:1"]
    assert sorted(k[3] for k in keys) == [0, 1]


# ----------------------------------------------------------------------------- container
def test_container_is_the_subtree_under_the_parent_of_the_common_ancestor():
    els = [el(0, (0, 0, 400, 800), "a:1:1"),
           el(1, (0, 0, 400, 300), "a:2:1", parent=0),              # section: the container root (parent of the promo)
           el(2, (0, 0, 400, 100), "a:3:1", parent=1),              # promo (finding element)
           el(3, (0, 0, 100, 40), "a:4:1", "p", "x", parent=2),
           el(4, (0, 120, 400, 200), "a:5:1", parent=1),            # sibling of the promo: also under the container
           el(5, (0, 400, 400, 500), "a:6:1", parent=0)]            # elsewhere on the page
    c = Candidate(type="viewport_protrusion", state_key="/|400", tile=0, elements=[2], metrics={})
    assert container_locs(cap(els), c) == {"a:2:1", "a:3:1", "a:4:1", "a:5:1"}


def test_container_of_two_elements_uses_their_nearest_common_ancestor_and_remaps():
    els = [el(0, (0, 0, 400, 800), "a:1:1"), el(1, (0, 0, 400, 300), "a:20:1", parent=0),
           el(2, (0, 0, 100, 50), "a:21:1", parent=1), el(3, (0, 60, 100, 90), "a:22:1", parent=1)]
    c = Candidate(type="collision", state_key="/|400", tile=0, elements=[2, 3], metrics={})
    got = container_locs(cap(els), c, {"a": []})
    assert got == {"a:1:1", "a:20:1", "a:21:1", "a:22:1"}                  # common ancestor's parent is the page root


def test_ancestors_of_the_fixed_region_may_grow_taller_but_not_wider():
    chain = [el(0, (0, 0, 400, 600), "a:1:1"), el(1, (0, 0, 400, 300), "a:2:1", parent=0)]
    taller = [el(0, (0, 0, 400, 700), "a:1:1"), el(1, (0, 0, 400, 400), "a:2:1", parent=0)]
    wider = [el(0, (0, 0, 460, 700), "a:1:1"), el(1, (0, 0, 400, 400), "a:2:1", parent=0)]
    grow = {"a:1:1"}
    assert layout_drift(cap(chain), cap(taller), None, set()) == {"a:1:1", "a:2:1"}          # without the allowance
    assert layout_drift(cap(chain), cap(taller), None, {"a:2:1"}, grow=grow) == set()          # growing taller is the fix at work
    assert layout_drift(cap(chain), cap(wider), None, {"a:2:1"}, grow=grow) == {"a:1:1"}        # a sideways change still counts


def test_ancestor_locs_walks_up_from_the_container():
    els = [el(0, (0, 0, 400, 800), "a:1:1"), el(1, (0, 0, 400, 300), "a:2:1", parent=0),
           el(2, (0, 0, 400, 100), "a:3:1", parent=1), el(3, (0, 0, 100, 40), "a:4:1", "p", "x", parent=2)]
    c = Candidate(type="viewport_protrusion", state_key="/|400", tile=0, elements=[3], metrics={})
    # container root is the parent of the finding element (a:3:1); its ancestors are a:2:1 and a:1:1
    assert container_locs(cap(els), c) == {"a:3:1", "a:4:1"} and ancestor_locs(cap(els), c) == {"a:2:1", "a:1:1"}
