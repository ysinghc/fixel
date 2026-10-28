"""Opacity diff and pixel evidence against real renders: a painted overlap is observable, an invisible one is not."""
import asyncio

import pytest

from fixel.capture.browser import FREEZE_CSS, Browsers, capture_page, new_context
from fixel.detect.oracles import run_oracles
from fixel.detect.pixels import outside, pixel_evidence
from fixel.models import StateSpec
from fixel.store import ArtifactStore

RESET = "<style>*{box-sizing:border-box}body{margin:0;font:16px/1.4 sans-serif}</style>"


@pytest.fixture
def evidence(tmp_path):
    """evidence(html, type_, height=600) -> [(candidate, PixelEvidence)] for candidates of one type."""
    store = ArtifactStore(tmp_path)

    def run(html, type_, height=600):
        async def go():
            async with Browsers() as browser:
                page = await (await new_context(browser)).new_page()
                await page.set_viewport_size({"width": 375, "height": height})
                await page.set_content(html)
                await page.add_style_tag(content=FREEZE_CSS)
                cap = await capture_page(page, StateSpec(route="/t", width=375, height=height), store)
                return [(c, await pixel_evidence(page, cap, c)) for c in run_oracles(cap) if c.type == type_]
        return asyncio.run(go())
    return run


def test_painted_text_overlap_is_observable(evidence):
    html = RESET + ('<p style="margin:0">Overlapping line one</p>'
                    '<p style="margin:-14px 0 0;background:#fff;color:#c00">Overlapping line two</p>')
    (c, px), *_ = evidence(html, "collision")
    assert px.opacity_diff > 0.05 and px.observable


def test_invisible_overlap_is_not_observable(evidence):
    # the guide's invisible_overlap control: boxes collide but nothing is painted in the overlap
    html = RESET + ('<p style="margin:0;color:transparent">Overlapping line one</p>'
                    '<p style="margin:-14px 0 0;color:transparent">Overlapping line two</p>')
    results = evidence(html, "collision")
    assert results and all(not px.observable for _, px in results)


def test_banner_over_button_is_observable(evidence):
    html = RESET + ('<div style="height:480px"></div><button style="width:140px;height:44px">Checkout</button>'
                    '<div style="position:fixed;left:0;right:0;bottom:0;height:120px;background:#333;z-index:50"></div>')
    results = evidence(html, "occlusion", height=560)
    assert results and all(px.observable and px.opacity_diff > 0.5 for _, px in results)


def test_banner_with_its_own_text_elsewhere_still_covers_the_button(evidence):
    # regression: the banner's text box is far from the button's; coverage is through the full rectangle
    html = RESET + ('<div style="height:480px"></div><button style="width:140px;height:44px">Pay now</button>'
                    '<div style="position:fixed;left:0;right:0;bottom:0;height:120px;background:#333;color:#fff;'
                    'padding:8px;z-index:50">We use cookies</div>')
    results = evidence(html, "occlusion", height=560)
    assert results and all(px.observable and px.opacity_diff > 0.5 for _, px in results)


def test_painted_child_outside_card_is_observable(evidence):
    html = RESET + ('<div style="width:200px;height:60px;background:#eee;margin:10px">'
                    '<button style="width:160px;margin-left:120px;background:#06c;color:#fff">Pay now</button></div>')
    results = evidence(html, "element_protrusion")
    assert results and all(px.observable for _, px in results)


def test_unpainted_child_outside_card_is_not_observable(evidence):
    html = RESET + ('<div style="width:200px;height:60px;background:#eee;margin:10px">'
                    '<button style="width:160px;margin-left:120px;background:transparent;border:0;color:transparent">Pay</button></div>')
    results = evidence(html, "element_protrusion")
    assert results and all(not px.observable for _, px in results)


def test_outside_strips_cover_only_the_protruding_part():
    strips = outside((100, 10, 300, 50), (0, 0, 200, 100))        # child sticks out 100px on the right
    assert strips == [(200, 10, 300, 50)]
    assert outside((10, 10, 50, 50), (0, 0, 200, 100)) == []
