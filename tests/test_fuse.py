from fixel.detect.fuse import decide, finding_key, fuse, observable
from fixel.models import Candidate, Capture, Element, PixelEvidence, StateSpec, Tile, Triage


def el(id_, loc=None, tag="div", text="", parent=None):
    return Element(id=id_, parent=parent, tag=tag, loc=loc, rect=(0, 0, 10, 10), text_rect=None, text=text,
                   interactive=False, replaced=False, style={}, scroll=(0, 0, 0, 0))


def cap(width, elements):
    return Capture(state=StateSpec(route="/", width=width), vw=width, vh=800, doc_w=width,
                   tiles=[Tile(scroll_y=0, png_sha="x", elements=elements, occlusion={})], axe=[])


def cand(type_, ids, width):
    return Candidate(type=type_, state_key=f"/|{width}", tile=0, elements=ids, metrics={})


def tri(verdict, conf=0.9):
    return Triage(verdict=verdict, defect_type="collision", severity=2, what_the_user_sees="x", fix_hint="y", confidence=conf)


def px(obs, diff=None, spill=None):
    return PixelEvidence(opacity_diff=diff, sam_spill=spill, observable=obs)


def test_geometry_only_types_are_always_observable():
    for t in ("viewport_protrusion", "clipped_text", "contrast", "small_target"):
        assert observable(cand(t, [1], 320), px(False))


def test_collision_needs_a_visible_pixel_change():
    assert not observable(cand("collision", [1, 2], 320), px(False, diff=0.01))
    assert observable(cand("collision", [1, 2], 320), px(False, diff=0.2))


def test_occlusion_accepts_either_sam_spill_or_diff():
    assert observable(cand("occlusion", [1, 2], 320), px(False, spill=0.6))
    assert observable(cand("occlusion", [1, 2], 320), px(False, diff=0.3))
    assert not observable(cand("occlusion", [1, 2], 320), px(False))


def test_decide_policy():
    c = cand("collision", [1, 2], 320)
    assert decide(c, px(False), None) == "not_observable"
    assert decide(c, px(True), None) == "confirmed"                       # model down: geometry plus pixels stand
    assert decide(c, px(True), tri("real_defect")) == "confirmed"
    assert decide(c, px(True), tri("intentional", 0.9)) == "dismissed"
    assert decide(c, px(True), tri("intentional", 0.5)) == "confirmed"    # a low-confidence dismissal does not count
    assert decide(c, px(True), tri("unsure")) == "needs_review"
    assert decide(c, px(True), tri("not_visible")) == "needs_review"


def test_key_prefers_source_loc_then_tag_and_text_hash_and_ignores_order():
    by_id = {1: el(1, loc="src/A.jsx:3:5"), 2: el(2, tag="p", text="Hello"), 3: el(3, tag="p", text=" hello ")}
    k = finding_key(cand("collision", [2, 1], 320), by_id)
    assert k == finding_key(cand("collision", [1, 2], 320), by_id)
    assert k.startswith("collision|") and "src/A.jsx:3:5" in k
    assert finding_key(cand("collision", [2], 1), by_id) == finding_key(cand("collision", [3], 1), by_id)


def test_same_failure_across_widths_becomes_one_finding_with_a_range():
    items = [(cap(w, [el(1, "src/A.jsx:3:5")]), cand("viewport_protrusion", [1], w), px(True)) for w in (375, 320, 414)]
    (f,) = fuse(items)
    assert f.widths == [320, 375, 414] and f.status == "confirmed" and f.locs == ["src/A.jsx:3:5"]


def test_rows_from_one_map_share_a_loc_and_merge():
    c0 = cap(320, [el(1, "src/List.jsx:9:7"), el(2, "src/List.jsx:9:7")])
    items = [(c0, cand("small_target", [1], 320), px(True)), (c0, cand("small_target", [2], 320), px(True))]
    assert len(fuse(items)) == 1


def test_finding_takes_best_status_and_only_its_own_widths():
    e = [el(1, "src/A.jsx:1:1"), el(2, "src/B.jsx:2:2")]
    items = [(cap(320, e), cand("collision", [1, 2], 320), px(True, diff=0.3)),
             (cap(1280, e), cand("collision", [1, 2], 1280), px(False, diff=0.0))]
    (f,) = fuse(items)
    assert f.status == "confirmed" and f.widths == [320]                  # not reproduced visibly at 1280


def test_unobservable_everywhere_keeps_all_widths_and_sorts_last():
    e = [el(1, "src/A.jsx:1:1"), el(2, "src/B.jsx:2:2")]
    items = [(cap(w, e), cand("collision", [1, 2], w), px(False, diff=0.0)) for w in (320, 768)]
    items.append((cap(320, e), cand("viewport_protrusion", [1], 320), px(True)))
    fs = fuse(items)
    assert [f.status for f in fs] == ["confirmed", "not_observable"] and fs[1].widths == [320, 768]


def test_triage_dismissal_applies_per_finding():
    e = [el(1, "src/A.jsx:1:1"), el(2, "src/B.jsx:2:2")]
    items = [(cap(320, e), cand("collision", [1, 2], 320), px(True, diff=0.3))]
    key = fuse(items)[0].key
    (f,) = fuse(items, {key: tri("intentional", 0.95)})
    assert f.status == "dismissed" and f.triage.verdict == "intentional"
