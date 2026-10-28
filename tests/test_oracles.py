"""One positive and one negative HTML fixture per oracle (guide section 14.1)."""
from fixel.detect.oracles import run_oracles

RESET = "<style>*{box-sizing:border-box}body{margin:0;font:16px/1.4 sans-serif}</style>"


def types(cands, t):
    return [c for c in cands if c.type == t]


# --- viewport protrusion -------------------------------------------------------------------
def test_viewport_protrusion_fires_on_fixed_wide_child(found):
    c = found(RESET + '<div style="width:600px;height:40px;background:#ccc"><p>wide</p></div>', width=375)
    hits = types(c, "viewport_protrusion")
    assert hits and hits[0].metrics["overflow_px"] > 200


def test_viewport_protrusion_ignores_overflow_inside_scroller(found):
    c = found(RESET + '<div style="overflow-x:auto"><div style="width:900px;height:40px"><p>wide</p></div></div>', width=375)
    assert not types(c, "viewport_protrusion")


# --- clipped text --------------------------------------------------------------------------
def test_clipped_text_fires_on_hidden_overflow(found):
    c = found(RESET + '<div style="width:80px;height:20px;overflow:hidden;white-space:nowrap">A very long unbroken label here</div>')
    assert types(c, "clipped_text")


def test_clipped_text_allows_deliberate_ellipsis(found):
    c = found(RESET + '<div style="width:80px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">A very long unbroken label here</div>')
    assert not types(c, "clipped_text")


# --- collision -----------------------------------------------------------------------------
def test_collision_fires_on_overlapping_text(found):
    html = RESET + '<p style="margin:0">Overlapping line one</p><p style="margin:-14px 0 0">Overlapping line two</p>'
    assert types(found(html), "collision")


def test_collision_ignores_parent_child_and_separate_blocks(found):
    html = RESET + '<div style="padding:8px"><p>First paragraph</p><p>Second paragraph</p></div>'
    assert not types(found(html), "collision")


def test_collision_under_sticky_header_is_hinted_as_stacked(found):
    # content scrolled under a sticky nav collides by design; the hint lets triage dismiss it
    html = RESET + ('<nav style="position:sticky;top:0;height:40px;background:#fff"><span>Site name</span></nav>'
                    '<div style="height:20px"></div><p style="margin:-45px 0 0">Overlapping paragraph</p>')
    hits = types(found(html), "collision")
    assert hits and all(c.metrics["stacked"] == 1.0 for c in hits)


# --- element protrusion --------------------------------------------------------------------
def test_element_protrusion_fires_when_child_leaves_card(found):
    html = RESET + ('<div style="width:200px;height:60px;background:#eee;margin:10px">'
                    '<button style="width:160px;margin-left:120px">Pay now</button></div>')
    assert types(found(html), "element_protrusion")


def test_element_protrusion_ignores_contained_child(found):
    html = RESET + '<div style="width:200px;height:60px;background:#eee;margin:10px"><button>Pay</button></div>'
    assert not types(found(html), "element_protrusion")


def test_element_protrusion_ignores_fixed_banner_outside_body(found):
    # a fixed element is positioned against the viewport; body's box says nothing about it
    html = RESET + '<body style="background:#fff;height:100px"><p>short page</p><div style="position:fixed;left:0;right:0;bottom:0;height:80px;background:#222;color:#fff">cookies</div></body>'
    assert not types(found(html, height=900), "element_protrusion")


# --- occlusion -----------------------------------------------------------------------------
BANNER = '<div style="position:fixed;left:0;right:0;bottom:0;height:120px;background:#333;z-index:50{extra}"></div>'


def test_occlusion_fires_when_banner_covers_button(found):
    html = RESET + '<div style="height:480px"></div><button style="width:140px;height:44px">Checkout</button>' + BANNER.format(extra="")
    assert types(found(html, height=560), "occlusion")


def test_occlusion_blind_to_pointer_events_none_overlay(found):
    # documented blind spot: elementFromPoint ignores pointer-events:none, the pixel layer catches it
    html = RESET + '<div style="height:480px"></div><button style="width:140px;height:44px">Checkout</button>' + BANNER.format(extra=";pointer-events:none")
    assert not types(found(html, height=560), "occlusion")


def test_occlusion_absent_for_clear_button(found):
    html = RESET + '<button style="width:140px;height:44px">Checkout</button>'
    assert not types(found(html), "occlusion")


# --- small targets -------------------------------------------------------------------------
def test_small_target_fires_on_16px_icon_button(found):
    assert types(found(RESET + '<button style="width:16px;height:16px;padding:0"></button>'), "small_target")


def test_small_target_ignores_inline_link_in_text_and_big_button(found):
    html = RESET + '<p>Read the <a href="#">terms</a> first.</p><button style="width:48px;height:48px"></button>'
    assert not types(found(html), "small_target")


# --- contrast (axe-core) -------------------------------------------------------------------
def test_contrast_fires_on_low_contrast_text(found):
    assert types(found(RESET + '<p style="color:#bbb;background:#fff">Barely readable</p>'), "contrast")


def test_contrast_clean_for_dark_text(found):
    assert not types(found(RESET + '<p style="color:#111;background:#fff">Readable</p>'), "contrast")


# --- stamping ------------------------------------------------------------------------------
def test_candidates_are_stamped_with_state_and_tile(snap):
    cap = snap(RESET + '<div style="width:600px;height:40px"><p>wide</p></div>')
    for c in run_oracles(cap):
        assert c.state_key == cap.state.key and c.tile >= 0
