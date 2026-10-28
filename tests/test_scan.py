"""End-to-end geometry scan of the static fixture site, with the bugs planted in its HTML."""
import os
from pathlib import Path

import pytest

from fixel.cli import findings_of, scan_states, serve_static
from fixel.models import StateSpec
from fixel.store import ArtifactStore

SITE = Path(__file__).parent / "fixtures" / "site"


@pytest.fixture(scope="module")
def site():
    server, url = serve_static(SITE)
    yield url
    server.shutdown()


def widths_for(findings, type_, status="confirmed"):
    return {w for f in findings if f.type == type_ and f.status == status for w in f.widths}


async def test_fixed_width_banner_protrudes_only_on_narrow_viewports(site, tmp_path):
    states = [StateSpec(route="/index.html", width=w) for w in (320, 375, 1024, 1440)]
    found = findings_of(await scan_states(states, site, ArtifactStore(tmp_path)))
    assert widths_for(found, "viewport_protrusion") == {320, 375}
    assert widths_for(found, "small_target") == {320, 375, 1024, 1440}      # the 16px close button, everywhere


async def test_cookie_banner_occludes_pay_button_on_short_viewport(site, tmp_path):
    short = StateSpec(route="/checkout.html", width=375, height=560)
    tall = StateSpec(route="/checkout.html", width=375, height=1000)
    found = findings_of(await scan_states([short, tall], site, ArtifactStore(tmp_path)))
    (f,) = [f for f in found if f.type == "occlusion"]
    assert f.status == "confirmed" and f.widths == [375] and f.evidence[0].opacity_diff > 0.5     # pixels agree with hit testing


async def test_pseudo_localization_lengthens_text(site, tmp_path):
    plain, pseudo = [StateSpec(route="/index.html", width=1024, text_stress=t) for t in ("none", "pseudo")]
    cap_a, cap_b = [r.cap for r in await scan_states([plain, pseudo], site, ArtifactStore(tmp_path))]
    text = lambda cap: " ".join(e.text for e in cap.tiles[0].elements)
    assert len(text(cap_b)) > len(text(cap_a)) * 1.2
    assert "á" in text(cap_b) or "é" in text(cap_b)
