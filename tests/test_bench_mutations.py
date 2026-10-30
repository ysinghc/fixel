"""Each mutation operator, injected into a real page, makes the defect it promises (geometry-level sanity, not accuracy).

These tests check that an operator's injection works and that the oracles see what the operator's `hits` says. They are
regression tests for the benchmark's machinery; no detection number in a report comes from here (guide section 9.3).
"""
import asyncio
import random

import pytest

from fixel.bench.mutations import BY_NAME, OPS, inject, pick
from fixel.capture.browser import FREEZE_CSS, SNAPSHOT_JS, Browsers, capture_page, new_context
from fixel.detect.fuse import candidate_key
from fixel.detect.oracles import run_oracles
from fixel.models import StateSpec
from fixel.store import ArtifactStore

PNG = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='100' height='60'><rect width='100' height='60' fill='%23888'/></svg>"
PAGE = f"""<style>*{{box-sizing:border-box}}body{{margin:0;font:16px/1.4 sans-serif;background:#fff;color:#111}}</style>
<main data-loc="page.jsx:1:1" style="padding:12px;height:600px;position:relative">
  <h1 data-loc="page.jsx:2:1">Heading</h1>
  <p data-loc="page.jsx:3:1">First paragraph that is long enough to wrap onto several lines on a phone, so it can be clamped later on.</p>
  <p data-loc="page.jsx:4:1">Second paragraph sitting directly below the first one in the same container element.</p>
  <div data-loc="page.jsx:5:1" style="display:flex;gap:8px"><span data-loc="page.jsx:6:1">Left label</span><span data-loc="page.jsx:7:1">Right label</span></div>
  <div data-loc="page.jsx:8:1" style="width:200px;height:60px;background:#eee">A block</div>
  <button data-loc="page.jsx:9:1" style="width:120px;height:40px">Buy it now today</button>
  <img data-loc="page.jsx:10:1" src="{PNG}" width="100" height="60" alt="">
  <ul data-loc="page.jsx:11:1" style="display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0">
    {''.join(f'<li data-loc="page.jsx:{12 + i}:1" style="padding:4px 12px;border:1px solid #888;border-radius:12px">Chip number {i}</li>' for i in range(5))}
  </ul>
  <a data-loc="page.jsx:20:1" href="#" style="position:absolute;left:12px;top:540px;width:140px;height:40px;background:#ddd;display:block">Checkout</a>
</main>"""


def mutate(op_name: str, seed: int = 1):
    """-> (applied, baseline candidate keys, mutated candidates, mutated capture, target loc)"""
    op = BY_NAME[op_name]

    async def go():
        store = ArtifactStore("/tmp/fixel-test-bench-art")
        async with Browsers() as browser:
            ctx = await new_context(browser)
            spec = StateSpec(route="/t", width=375, height=600)

            async def fresh():
                page = await ctx.new_page()
                await page.set_viewport_size({"width": 375, "height": 600})
                await page.set_content(PAGE)
                await page.add_style_tag(content=FREEZE_CSS)
                return page

            page = await fresh()
            base = await capture_page(page, spec, store)
            base_keys = {candidate_key(base, c) for c in run_oracles(base)}
            chosen = pick(base, op, random.Random(seed))
            assert chosen, f"{op_name} found no target on the fixture page"
            tile, el = chosen
            page = await fresh()
            await page.evaluate(f"window.scrollTo(0, {base.tiles[tile].scroll_y})")
            snap = await page.evaluate(SNAPSHOT_JS)
            same = next(e for e in snap["elements"] if e["id"] == el.id)
            assert same["loc"] == el.loc and same["tag"] == el.tag       # a fresh render tags the same element with the same id
            applied = await inject(page, op, el.id)
            cap = await capture_page(page, spec, store)
            return applied, base_keys, run_oracles(cap), cap, el.loc
    return asyncio.run(go())


@pytest.mark.parametrize("name", [o.name for o in OPS if not o.control and o.name != "ghost_banner"])
def test_operator_injects_and_the_oracles_see_the_defect(name):
    applied, base_keys, cands, cap, loc = mutate(name)
    assert applied
    new = [c for c in cands if candidate_key(cap, c) not in base_keys]
    assert {c.type for c in new} & BY_NAME[name].hits, f"{name}: new candidates were {[(c.type, c.metrics) for c in new]}"


def test_ghost_banner_paints_but_hit_testing_is_blind_to_it():
    # the documented gap: occlusion starts from hit testing, so a pointer-events:none banner is not a candidate
    applied, base_keys, cands, cap, loc = mutate("ghost_banner")
    assert applied
    assert not [c for c in cands if c.type == "occlusion" and candidate_key(cap, c) not in base_keys]
    opaque = mutate("opaque_banner")
    assert [c for c in opaque[2] if c.type == "occlusion" and candidate_key(opaque[3], c) not in opaque[1]]


@pytest.mark.parametrize("name", ["badge_overlap", "open_dropdown", "invisible_overlap"])
def test_controls_inject(name):
    applied, *_ = mutate(name)
    assert applied and BY_NAME[name].control in ("dismissed", "not_observable")


def test_pick_is_reproducible_and_needs_a_source_location():
    async def go():
        store = ArtifactStore("/tmp/fixel-test-bench-art")
        async with Browsers() as browser:
            page = await (await new_context(browser)).new_page()
            await page.set_viewport_size({"width": 375, "height": 600})
            await page.set_content(PAGE)
            return await capture_page(page, StateSpec(route="/t", width=375, height=600), store)
    cap = asyncio.run(go())
    op = BY_NAME["fixed_width"]
    assert pick(cap, op, random.Random(5)) == pick(cap, op, random.Random(5))
    for t in cap.tiles:
        for e in t.elements:
            e.loc = None                                 # without data-loc nothing is a valid target
    assert pick(cap, op, random.Random(5)) is None
