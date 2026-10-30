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


async def scan_states(states: list[StateSpec], base_url: str, store: ArtifactStore, parallel: int = 4,
                      progress=None, sam: bool = False) -> list[Scanned]:
    """Capture each state, run the geometry oracles, then the opacity diff (and SAM if asked) while the page is open."""
    results: list[Scanned] = []
    sem = asyncio.Semaphore(parallel)
    async with Browsers() as browser:
        async def one(s: StateSpec):
            async with sem:
                ctx = await new_context(browser)
                try:
                    page, cap = await capture(ctx, base_url, s, store)
                    cands = run_oracles(cap)
                    evidence = [await pixel_evidence(page, cap, c) for c in cands]
                    await page.close()
                    if sam and cands:
                        try:
                            evidence = await add_sam(cap, cands, evidence, store)
                        except Exception as e:                  # model down, replay miss, no key: keep geometry + diff
                            warn_once(f"SAM evidence skipped ({type(e).__name__}: {str(e)[:80]})")
                finally:
                    await ctx.close()
                results.append(Scanned(cap, cands, evidence))
                if progress:
                    progress(s, len(cands))
        await asyncio.gather(*(one(s) for s in states))
    results.sort(key=lambda r: r.cap.state.key)
    return results


def findings_of(results: list[Scanned], triage: dict[str, Triage] | None = None) -> list[Finding]:
    return fuse([(r.cap, c, e) for r in results for c, e in zip(r.candidates, r.evidence)], triage)


async def triage_findings(results: list[Scanned], findings: list[Finding], store: ArtifactStore,
                          model: str = "muse-spark-1.3", limit: int = 60, parallel: int = 4) -> dict[str, Triage]:
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
            try:
                out[key] = await triage_candidate(cap, c, e, store, model)
            except Exception as ex:                             # that finding keeps geometry + pixels (decide(): tri=None)
                warn_once(f"triage skipped for some findings ({type(ex).__name__}: {str(ex)[:80]})")

    todo = [f.key for f in findings if f.status == "confirmed" and f.key in best][:limit]
    await asyncio.gather(*(one(k) for k in todo))
    return out
