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


def test_viewport_protrusion_fires_when_the_root_clips_sideways_overflow(found):
    # a fixed bar wider than the screen never makes the page scroll, so the old gate missed it; the cut-off text is a defect
    c = found(RESET + '<style>body{overflow-x:hidden}</style><nav style="position:fixed;left:0;top:0;width:600px;height:40px;background:#ccc"><a href="#" style="margin-left:330px">Home link</a></nav>', width=375)
    hits = types(c, "viewport_protrusion")
    assert hits and hits[0].metrics["clipped_by_root"] == 1.0


def test_root_clipped_page_ignores_decorative_blobs_and_clipping_carousels_and_closed_drawers(found):
    html = RESET + ('<style>body{overflow-x:hidden}</style>'
                    '<div style="position:absolute;left:300px;top:0;width:200px;height:200px;background:#eee"></div>'      # no text: decorative
                    '<div style="overflow:hidden;width:300px"><div style="width:900px;height:40px"><p>slide</p></div></div>'  # carousel
                    '<aside style="position:absolute;left:400px;top:80px;width:200px"><a href="#">Menu item</a></aside>')    # off screen
    assert not types(found(html, width=375), "viewport_protrusion")


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


# --- transient (scrollable apart) ---------------------------------------------------------
STICKY_NAV = '<nav style="position:sticky;top:0;height:56px;background:#fff"><span>Site name</span></nav>'


def test_sticky_nav_over_scrolled_content_is_transient(snap):
    # 3 screens of content: scroll the page to the end and the footer link sits under the nav only transiently
    # the link lands at y=15 in the third 600px tile, under the nav's text
    html = RESET + STICKY_NAV + '<div style="height:1159px"></div><a href="#" style="display:block">Footer link text</a><div style="height:900px"></div>'
    cap = snap(html, width=375, height=600)
    hits = [c for c in run_oracles(cap) if c.type in ("collision", "occlusion")]        # the nav covers the link: one defect
    assert hits and all(c.metrics.get("transient") for c in hits) and cap.doc_h > 2000


def test_cookie_banner_over_last_button_is_not_transient(snap):
    html = RESET + ('<div style="height:480px"></div><button style="width:140px;height:44px">Checkout</button>'
                    '<div style="position:fixed;left:0;right:0;bottom:0;height:120px;background:#333;z-index:50">cookies</div>')
    cands = run_oracles(snap(html, width=375, height=560))
    occ = [c for c in cands if c.type == "occlusion"]
    assert occ and not any(c.metrics.get("transient") for c in occ)      # no scroll position clears the final button


def test_fixed_banner_over_mid_page_content_is_transient(snap):
    html = RESET + ('<div style="height:300px"></div><button style="width:140px;height:44px">Mid page</button>'
                    '<div style="height:1200px"></div>'
                    '<div style="position:fixed;left:0;right:0;bottom:0;height:200px;background:#333;z-index:50"></div>')
    occ = [c for c in run_oracles(snap(html, width=375, height=500)) if c.type == "occlusion"]
    assert occ and all(c.metrics.get("transient") for c in occ)          # scroll the button above the banner


# --- on-screen filtering ------------------------------------------------------------------
def test_candidates_are_reported_only_in_tiles_where_the_element_is_on_screen(snap):
    # a 16px button 1500px down a page: it must be reported in the tile that shows it, not in the 6 others
    html = RESET + '<div style="height:1500px"></div><button style="width:16px;height:16px;padding:0"></button><div style="height:600px"></div>'
    cap = snap(html, width=375, height=600)
    tiles = {c.tile for c in run_oracles(cap) if c.type == "small_target"}
    assert tiles == {2}                                         # y=1500 is inside the third 600px tile (1200-1800)


def test_contrast_is_placed_in_the_tile_that_shows_the_element(snap):
    html = RESET + '<div style="height:1300px"></div><p style="color:#bbb;background:#fff">Barely readable</p><div style="height:600px"></div>'
    cap = snap(html, width=375, height=600)
    assert [c.tile for c in run_oracles(cap) if c.type == "contrast"] == [2]


# --- grouping protruding siblings under their parent ---------------------------------------
def test_siblings_that_protrude_because_their_parent_does_are_reported_once_as_the_parent(snap):
    html = RESET + ('<div id="card" style="width:600px;background:#eee"><h2>Title</h2><p>One paragraph</p><p>Another paragraph</p></div>')
    cap = snap(html, width=375)
    hits = [c for c in run_oracles(cap) if c.type == "viewport_protrusion"]
    by_id = {e.id: e for e in cap.tiles[0].elements}
    assert len(hits) == 1 and [by_id[i].tag for i in hits[0].elements] == ["div"]      # the card, not its three children


def test_a_single_protruding_child_is_still_the_culprit(snap):
    html = RESET + '<div style="width:300px"><p style="white-space:nowrap">A long unbroken line of text that cannot wrap and runs past the edge</p></div>'
    hits = [c for c in run_oracles(snap(html, width=375)) if c.type == "viewport_protrusion"]
    assert len(hits) == 1


# --- one defect, one key -------------------------------------------------------------------
BANNER_WITH_TEXT = ('<div style="height:480px"></div><button style="width:140px;height:44px">Checkout</button>'
                    '<div style="position:fixed;left:0;right:0;bottom:0;height:120px;background:#333;color:#fff;padding:8px;z-index:50">'
                    '<p style="margin:0">We use cookies</p></div>')


def test_the_coverer_is_named_by_its_fixed_root_not_by_the_inner_element_that_was_hit(snap):
    cap = snap(RESET + BANNER_WITH_TEXT, width=375, height=560)
    tile = cap.tiles[0]
    by_id = {e.id: e for e in tile.elements}
    (occ,) = [c for c in run_oracles(cap) if c.type == "occlusion" and c.tile == 0]
    assert [by_id[i].tag for i in occ.elements] == ["button", "div"]            # the banner box, not its <p>
    assert by_id[occ.elements[1]].style["position"] == "fixed"


def test_a_collision_already_explained_by_an_occlusion_is_not_reported_twice(snap):
    cands = run_oracles(snap(RESET + BANNER_WITH_TEXT, width=375, height=560))
    assert [c for c in cands if c.type == "occlusion"]
    assert not [c for c in cands if c.type == "collision"]                      # button text vs banner text: same defect


def test_unrelated_collisions_survive_next_to_an_occlusion(snap):
    html = RESET + '<p style="margin:0">Overlapping line one</p><p style="margin:-14px 0 0">Overlapping line two</p>' + BANNER_WITH_TEXT
    cands = run_oracles(snap(html, width=375, height=560))
    assert [c for c in cands if c.type == "collision"]                          # the two paragraphs still collide
