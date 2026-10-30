"""Model-free verifier (guide section 7.5): did the patch really fix the finding, and break nothing?

It re-renders the finding's route across the whole width x theme x text-stress matrix and compares against a
baseline scan of the same states taken at HEAD with the same model-free settings. It never calls a language model or
SAM, so a pass cannot be argued into existence and a re-run gives the same answer.

Passed means all of: the target finding is gone in every state, no new finding appeared, nothing outside the fixed
container moved sideways or changed size, the build passes, and the linter accepts the diff.
"""
from ..config import Matrix
from ..detect.fuse import candidate_key
from ..fix.lint import lint
from ..fix.worktree import Workspace
from ..models import Finding, StateSpec, Verification
from ..scan import Scanned, findings_of, scan_states
from ..store import ArtifactStore
from .drift import ancestor_locs, container_locs, layout_drift, line_remap, remap_key

WIDTHS = [320, 375, 414, 768, 1024, 1280, 1440]


def route_of(f: Finding) -> str:
    """The route the finding was seen on (state keys are `route|width|theme|stress|n`)."""
    return f.candidates[0].state_key.split("|")[0]


def matrix_states(route: str, matrix: Matrix | None = None) -> list[StateSpec]:
    m = matrix or Matrix()
    return [StateSpec(route=route, width=w, height=m.height, theme=t, text_stress=s)
            for w in m.widths for t in m.themes for s in m.text_stress]


def confirmed_keys(results: list[Scanned]) -> set[str]:
    """Findings that stand on geometry plus pixels alone (no SAM, no triage)."""
    return {f.key for f in findings_of(results) if f.status == "confirmed"}


async def scan_baseline(ws: Workspace, states: list[StateSpec], store: ArtifactStore, parallel: int = 4) -> list[Scanned]:
    """The model-free scan of the pristine worktree, to compare a patch against."""
    return await scan_states(states, ws.url, store, parallel, sam=False)


async def verify(f: Finding, ws: Workspace, baseline: list[Scanned], store: ArtifactStore, parallel: int = 4,
                 emit=None) -> Verification:
    states = [r.cap.state for r in baseline]
    diff = await ws.diff()
    remap = line_remap(diff)                              # the patch shifts data-loc line numbers
    notes: list[str] = []

    async def say(item: str, ok: bool) -> None:
        if emit:
            await emit({"type": "fix.verify", "item": item, "ok": ok})

    errs = lint(diff, ws.allowed_files)
    lint_ok = not errs
    notes += [f"lint: {e}" for e in errs]
    await say("lint", lint_ok)

    target = remap_key(f.key, remap)

    async def state_done(r: Scanned) -> None:
        if emit:                                          # the proof grid fills cell by cell as states are re-rendered
            await emit({"type": "fix.verify.state", "state_key": r.cap.state.key, "ok": target not in confirmed_keys([r])})

    after = await scan_states(states, ws.url, store, parallel, sam=False, on_state=state_done)
    now = confirmed_keys(after)
    before = {remap_key(k, remap) for k in confirmed_keys(baseline)}
    grid = {r.cap.state.key: target not in confirmed_keys([r]) for r in after}
    target_gone = target not in now
    new_findings = sorted(now - before)
    await say("target_gone", target_gone)
    await say("no_new_findings", not new_findings)

    base_by_state = {r.cap.state.key: r for r in baseline}
    cand_src = next(((r.cap, c) for r in baseline for c in r.candidates if candidate_key(r.cap, c) == f.key), None)
    exclude = container_locs(*cand_src, remap) if cand_src else set()
    grow = ancestor_locs(*cand_src, remap) if cand_src else set()
    drifted = sorted({d for r in after if (b := base_by_state.get(r.cap.state.key))
                      for d in layout_drift(b.cap, r.cap, remap, exclude, grow=grow)})
    await say("no_drift", not drifted)

    build_ok = True
    if ws.target.build_cmd:
        build_ok, out = await ws.run(["sh", "-c", ws.target.build_cmd])
        if not build_ok:
            notes.append("build failed: " + "\n".join(out.strip().splitlines()[-12:]))
    await say("build", build_ok)

    tile_idx = cand_src[1].tile if cand_src else 0           # the tile that shows the target element
    shots = {r.cap.state.key: r.cap.tiles[min(tile_idx, len(r.cap.tiles) - 1)].png_sha for r in after if r.cap.tiles}
    return Verification(target_gone=target_gone, new_findings=new_findings, drifted=drifted, build_ok=build_ok,
                        lint_ok=lint_ok, grid=grid, shots=shots, notes=notes)
