# Fixel

Visual layout bug finder and fixer. The full plan is `docs/IMPLEMENTATION_GUIDE.md`; read the relevant section before implementing a module. Everything is a stub until built, and API details marked **[verify]** in the guide are unconfirmed.

## Architecture in one paragraph

Python backend (FastAPI, asyncio, Playwright) plus a React UI. Pipeline: plan states (route × width × theme × text stress) → capture (viewport tiles + DOM snapshot + axe) → geometry oracles → pixel evidence (SAM 3.1 box prompts + opacity diff) → Spark 1.3 triage → fuse and group into findings → localize to source (`data-loc`, CDP matched rules) → Wonder fix agent in a git worktree → patch linter → model-free verifier → report. Module map: guide section 5.

## Rules that must not be broken

- **Decisions are code, not prompts.** Finding status, whether a patch is allowed, and whether it worked are decided by deterministic code. Models can only narrow or dismiss; Spark can dismiss a candidate but never create one.
- **The verifier is model-free.** It uses oracles and the opacity diff only; no language model and no SAM, so a pass is reproducible.
- **No symptom-hiding patches.** The linter in `fix/lint.py` blocks `display:none`, new `overflow:hidden`, `!important`, `md:hidden`-style hiding, copy edits, new or deleted files, and files outside the localized set. It errs strict.
- **Never edit the user's branch.** Fixes run in an isolated git worktree under `.fixel/wt/`; approved patches are exported as `.patch`.
- **Every model call goes through `meta/client.py`'s `call()`**, the disk cache with `live`/`record`/`replay` modes. Cache keys use image SHAs, never bytes. Replay must never spend credits.
- **Contributor-tier models only on synthetic or public data.** Their prompts and completions train Meta models; never send private code.
- **Be honest in outputs:** report test-split numbers only, label injected bugs as injected, and mark replay mode.
- Benchmark headline numbers come from human labels and construction-based cases, never from the oracles grading themselves (guide section 9.3).

## Conventions

- Data crossing a module boundary is a pydantic model (`backend/fixel/models.py`).
- Oracles are pure functions over a snapshot with no I/O, each with a positive and a negative HTML fixture test.
- Python 3.11+, asyncio throughout; in-page JS lives in `.js` files beside the Python that calls it.
- Secrets live in `.env` (gitignored); `.env.example` documents the variables.

## Commands

- `make install`: install the package with dev extras and Chromium.
- `make test`: run pytest.
- `make demo-smoke`: run the demo path from cache (`FIXEL_MODE=replay`); the test it runs is not written yet.

## Build order and cut order

Protect a working scan-to-verified-fix loop first, then evidence, then extras (guide section 13). If behind, cut: synthetic corpus → explorer → voice intake → grounding chip. Never cut: the model-free verifier, the linter, the human-labelled benchmark, replay mode.
