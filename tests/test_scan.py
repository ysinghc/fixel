"""End-to-end geometry scan of the static fixture site, with the bugs planted in its HTML."""
import os
from pathlib import Path

import pytest

from fixel.cli import scan_states, serve_static, summarize
from fixel.models import StateSpec
from fixel.store import ArtifactStore

SITE = Path(__file__).parent / "fixtures" / "site"


@pytest.fixture(scope="module")
def site():
    server, url = serve_static(SITE)
    yield url
    server.shutdown()


def widths_for(rows, type_):
    return {w for r in rows if r["type"] == type_ for w in r["widths"]}


async def test_fixed_width_banner_protrudes_only_on_narrow_viewports(site, tmp_path):
    states = [StateSpec(route="/index.html", width=w) for w in (320, 375, 1024, 1440)]
    rows = summarize(await scan_states(states, site, ArtifactStore(tmp_path)))
    assert widths_for(rows, "viewport_protrusion") == {320, 375}
    assert widths_for(rows, "small_target") == {320, 375, 1024, 1440}      # the 16px close button, everywhere


async def test_cookie_banner_occludes_pay_button_on_short_viewport(site, tmp_path):
    short = StateSpec(route="/checkout.html", width=375, height=560)
    tall = StateSpec(route="/checkout.html", width=375, height=1000)
    rows = summarize(await scan_states([short, tall], site, ArtifactStore(tmp_path)))
    assert any(r["type"] == "occlusion" and r["widths"] == [375] and r["states"] == 1 for r in rows)


async def test_pseudo_localization_lengthens_text(site, tmp_path):
    plain, pseudo = [StateSpec(route="/index.html", width=1024, text_stress=t) for t in ("none", "pseudo")]
    (cap_a, _), (cap_b, _) = await scan_states([plain, pseudo], site, ArtifactStore(tmp_path))
    text = lambda cap: " ".join(e.text for e in cap.tiles[0].elements)
    assert len(text(cap_b)) > len(text(cap_a)) * 1.2
    assert "á" in text(cap_b) or "é" in text(cap_b)
