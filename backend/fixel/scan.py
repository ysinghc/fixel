"""Scanning: capture each state, run the oracles and pixel evidence, fuse into findings (guide sections 6.2-6.6).

Used by `fixel scan` and by the verifier, which runs it model-free (sam=False, no triage) so a pass is reproducible.
"""
import asyncio
import functools
import http.server
import threading
from pathlib import Path
from typing import NamedTuple

from .capture.browser import Browsers, capture, new_context
from .detect.fuse import candidate_key, fuse
from .detect.oracles import run_oracles
from .detect.pixels import add_sam, pixel_evidence
from .detect.triage import triage_candidate
from .meta import client as meta
from .models import Candidate, Capture, Finding, PixelEvidence, StateSpec, Triage
from .store import ArtifactStore


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs) -> None:
        pass


def serve_static(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    """Serve a directory on a free local port (for fixture sites and built apps)."""
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class Scanned(NamedTuple):
    cap: Capture
    candidates: list[Candidate]
    evidence: list[PixelEvidence]


def models_available() -> bool:
    """True when a model call can be attempted: replay serves the cache, other modes need a key."""
    if meta.mode() == "replay":
        return True
    try:
        meta.api_key()
        return True
    except KeyError:
        return False


def warn_once(msg: str, _seen: set = set()) -> None:
    if msg not in _seen:
        _seen.add(msg)
        print(f"  warning: {msg}")


def state_event(s: StateSpec) -> dict:
    return {"state_key": s.key, "route": s.route, "width": s.width, "height": s.height, "theme": s.theme,
            "text_stress": s.text_stress}


def captured_event(cap: Capture) -> dict:
    return {**state_event(cap.state), "vw": cap.vw, "vh": cap.vh, "doc_w": cap.doc_w, "doc_h": cap.doc_h,
            "tiles": [{"index": i, "sha": t.png_sha, "scroll_y": t.scroll_y} for i, t in enumerate(cap.tiles)]}


def candidate_event(cap: Capture, c: Candidate, idx: int) -> dict:
    """Where a candidate is, in tile-viewport pixels, so the UI can draw it over the screenshot."""
    by_id = {e.id: e for e in cap.tiles[c.tile].elements}
    return {"state_key": cap.state.key, "idx": idx, "defect": c.type, "tile": c.tile, "metrics": c.metrics,
            "elements": [{"id": i, "tag": by_id[i].tag, "rect": by_id[i].rect, "loc": by_id[i].loc,
                          "text": by_id[i].text[:60]} for i in c.elements if i in by_id]}


async def scan_states(states: list[StateSpec], base_url: str, store: ArtifactStore, parallel: int = 4,
                      progress=None, sam: bool = False, emit=None, on_state=None, should_stop=None) -> list[Scanned]:
    """Capture each state, run the geometry oracles, then the opacity diff (and SAM if asked) while the page is open.

    emit(event) publishes each stage as it happens (state.started, state.captured, candidate.found, pixels.done, and the
    model.start/model.call events of SAM); on_state(Scanned) is called as each state finishes; should_stop() ends the
    scan early (a spent budget, a cancel) by skipping states that have not started."""
    results: list[Scanned] = []
    sem = asyncio.Semaphore(parallel)

    async def say(ev: dict) -> None:
        if emit:
            await emit(ev)

    async with Browsers() as browser:
        async def one(s: StateSpec):
            async with sem:
                if should_stop and should_stop():
                    return
                await say({"type": "state.started", **state_event(s)})
                ctx = await new_context(browser)
                try:
                    page, cap = await capture(ctx, base_url, s, store)
                    await say({"type": "state.captured", **captured_event(cap)})
                    cands = run_oracles(cap)
                    for i, c in enumerate(cands):
                        await say({"type": "candidate.found", **candidate_event(cap, c, i)})
                    evidence = [await pixel_evidence(page, cap, c) for c in cands]
                    await page.close()
                    if sam and cands and not (should_stop and should_stop()):
                        try:
                            evidence = await add_sam(cap, cands, evidence, store, emit)
                        except Exception as e:                  # model down, replay miss, no key: keep geometry + diff
                            warn_once(f"SAM evidence skipped ({type(e).__name__}: {str(e)[:80]})")
                            await say({"type": "model.error", "kind": "sam.box", "error": f"{type(e).__name__}: {str(e)[:120]}"})
                    for i, (c, e) in enumerate(zip(cands, evidence)):
                        await say({"type": "pixels.done", "state_key": cap.state.key, "idx": i, "evidence": e.model_dump()})
                finally:
                    await ctx.close()
                scanned = Scanned(cap, cands, evidence)
                results.append(scanned)
                if on_state:
                    await on_state(scanned)
                await say({"type": "state.done", "state_key": cap.state.key})    # the capture is saved: clients may fetch it now
                if progress:
                    progress(s, len(cands))
        await asyncio.gather(*(one(s) for s in states))
    results.sort(key=lambda r: r.cap.state.key)
    return results


def findings_of(results: list[Scanned], triage: dict[str, Triage] | None = None) -> list[Finding]:
    return fuse([(r.cap, c, e) for r in results for c, e in zip(r.candidates, r.evidence)], triage)


async def triage_findings(results: list[Scanned], findings: list[Finding], store: ArtifactStore,
                          model: str = "muse-spark-1.3", limit: int = 60, parallel: int = 4, emit=None,
                          should_stop=None) -> dict[str, Triage]:
    """One Spark call per confirmed finding, on its narrowest-width observable candidate (cost control)."""
    best: dict[str, tuple] = {}
    for r in results:
        for c, e in zip(r.candidates, r.evidence):
            k = candidate_key(r.cap, c)
            if e.observable and (k not in best or r.cap.state.width < best[k][0].state.width):
                best[k] = (r.cap, c, e)
    out: dict[str, Triage] = {}
    sem = asyncio.Semaphore(parallel)

    async def one(key: str):
        cap, c, e = best[key]
        async with sem:
            if should_stop and should_stop():
                return
            try:
                out[key] = await triage_candidate(cap, c, e, store, model, emit)
                if emit:
                    await emit({"type": "triage.done", "key": key, "triage": out[key].model_dump()})
            except Exception as ex:                             # that finding keeps geometry + pixels (decide(): tri=None)
                warn_once(f"triage skipped for some findings ({type(ex).__name__}: {str(ex)[:80]})")
                if emit:
                    await emit({"type": "model.error", "kind": "spark.triage", "key": key,
                                "error": f"{type(ex).__name__}: {str(ex)[:120]}"})

    todo = [f.key for f in findings if f.status == "confirmed" and f.key in best][:limit]
    await asyncio.gather(*(one(k) for k in todo))
    return out
