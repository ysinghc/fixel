"""Spike 2 (guide section 13): Spark structured triage on real candidates.

Checks: strict json_schema output works with two images, the reasoning-effort parameter name, response time,
and whether verdicts match what a person sees. Run: python scripts/spikes/spark_triage.py [--model muse-spark-1.3]
Calls are cached under .fixel/cache, so a rerun costs nothing.
"""
import argparse
import asyncio
import time
from pathlib import Path

from fixel import config as cfg
from fixel.cli import scan_states, serve_static
from fixel.detect.oracles import box
from fixel.detect.triage import crop_and_thumb, evidence_dict, triage
from fixel.models import StateSpec
from fixel.store import ArtifactStore
from fixel.target import TargetServer

SITE = Path("tests/fixtures/site")


async def cases(store):
    """(label, expected, cap, candidate, evidence) picked from real scans."""
    out = []
    server, url = serve_static(SITE)
    try:
        for label, expected, spec, want in [
            ("fixture: cookie banner over Pay button", "real_defect", StateSpec(route="/checkout.html", width=375, height=560), "occlusion"),
            ("fixture: 480px promo overflows phone", "real_defect", StateSpec(route="/index.html", width=320), "viewport_protrusion"),
            ("fixture: 16px close button", "real_defect", StateSpec(route="/index.html", width=1280), "small_target"),
        ]:
            r = (await scan_states([spec], url, store))[0]
            for c, e in zip(r.candidates, r.evidence):
                if c.type == want and e.observable:
                    out.append((label, expected, r.cap, c, e))
                    break
    finally:
        server.shutdown()
    conf = cfg.load("targets/iiitu-acm.yaml")
    async with TargetServer(conf.target) as url:
        r = (await scan_states([StateSpec(route="/", width=320)], url, store))[0]
    picked = {"collision": 0}
    for c, e in zip(r.candidates, r.evidence):
        if c.type == "collision" and e.observable and picked["collision"] < 2 and c.metrics.get("stacked") == 1.0:
            picked["collision"] += 1
            out.append(("iiitu-acm: footer link under sticky nav", "intentional", r.cap, c, e))
    return out


async def main(model: str):
    store = ArtifactStore()
    events = []

    async def emit(ev):
        events.append(ev)

    ok = 0
    items = await cases(store)
    for label, expected, cap, c, px in items:
        tile = cap.tiles[c.tile]
        by_id = {x.id: x for x in tile.elements}
        rects = [box(by_id[i]) if c.type == "collision" else by_id[i].rect for i in c.elements[:2] if i in by_id]
        crop, thumb = crop_and_thumb(store.get(tile.png_sha), rects)
        t0 = time.time()
        t = await triage(crop, thumb, evidence_dict(cap, c, px), model, emit)
        ok += t.verdict == expected
        print(f"\n{label}\n  expected={expected:<12} got={t.verdict:<12} type={t.defect_type} sev={t.severity} "
              f"conf={t.confidence:.2f}  ({time.time() - t0:.1f}s, {events[-1]['source']})\n  sees: {t.what_the_user_sees}\n  hint: {t.fix_hint}")
    print(f"\n{ok}/{len(items)} verdicts matched expectation; usage of last call: {events[-1]['usage']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="muse-spark-1.3")
    asyncio.run(main(ap.parse_args().model))
