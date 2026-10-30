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

- `make install`: install the package with dev extras, `npm install` (axe-core) and Chromium.
- `make test`: run pytest. Oracle and scan tests drive real Chromium; set `FIXEL_CHROMIUM_PATH` to a Chromium binary if Playwright's own download is absent (the test conftest defaults it to `/opt/pw-browsers/chromium` when present).
- `fixel scan --static tests/fixtures/site --route /index.html --widths 320 1440`: geometry-only scan of the planted-bug fixture site. Without `--static`, it scans the running app at `target.base_url`.
- `make targets`: init the target submodules and `npm install` each app. Then `fixel scan --config targets/iiitu-acm.yaml` starts that app's dev server itself (with the data-loc plugin), scans it, and stops it.
- `fixel fix --config targets/demo-shop.yaml --list`: scan the target in an isolated worktree and list the confirmed findings; then `--index N` or `--finding <text in key>` runs the fix agent on one (live model calls). Exports a `.patch` only if the model-free verifier passes.
- `make demo-smoke`: run the demo path from cache (`FIXEL_MODE=replay`); the test it runs is not written yet.

## Status

The scan-to-verified-fix loop works end to end. `fixel scan` detects (geometry oracles, opacity diff, SAM 3.1, Spark triage, fusion) and `fixel fix` repairs: an isolated git worktree, a Wonder tool-calling agent whose edits pass the symptom-hiding linter, and a model-free verifier over the whole width x theme matrix. Verified live on all three planted defects of `targets/demo-shop` (see `docs/SPIKES.md`).

Built: `models.py`, `store.py`, `config.py`, `env.py`, `target.py`, `scan.py`, `cli.py`, `meta/{client,sam}.py`, `capture/`, `detect/{oracles,pixels,triage,fuse}.py`, `localize/cdp_styles.py`, `fix/{lint,worktree,tools,agent}.py`, `verify/{drift,matrix}.py`, and the data-loc Vite plugin in `tooling/`. Targets are in `targets/`: development `iiitu-acm`, `pastebin`; test `aavesh`, `e-broker` (Next.js: no data-loc yet); plus the vendored planted-defect `demo-shop`. Never tune on the test split.

Still stubs: `api/server.py` (REST + event stream), the React UI (`web/`), `bench/` (mutations, corpus, metrics, ablations), `explore/cua.py`, `meta/{voice,image,spark}.py`. Next in the build plan (guide section 13): API and event stream, then the UI, then the benchmark and human labelling.

## Deviations from the guide

- `cand()` in `detect/oracles.py` returns a Candidate with `state_key=""` and `tile=-1`; `run_oracles(cap)` stamps both (the guide's snippet calls `cand` without the state, which `Candidate` requires).
- `element_protrusion` skips `position: fixed` children: they are laid out against the viewport, so parent containment is meaningless (a cookie banner was reported as protruding from `<body>`).
- `meta/client.py` creates the OpenAI client lazily and reads `FIXEL_MODE` per call, so replay and tests need no API key.
- `capture()` is split into `prepare()` + `capture_page()` so tests can tile a page loaded with `set_content`.
- `route_url`, `is_stacked`, `PSEUDO_LOC_JS` and `replay_step` were referenced but not defined in the guide. Pseudo-localization doubles and accents vowels (about +35% length); `replay_step` raises `NotImplementedError` until the explorer (guide section 8.2) is built.

- **data-loc is injected by a standalone Vite plugin, not the guide's `react({ babel: { plugins } })`.** `@vitejs/plugin-react` v6 (Vite 8) dropped Babel, so the guide's route fails on the dev-split targets. `tooling/vite-plugin-data-loc.mjs` runs Babel itself before the framework transform and works with plugin-react v4/v5/v6 and the SWC plugin; `tooling/vite.config.fixel.mjs` wraps the target's own config (path in `FIXEL_TARGET_CONFIG`), so target files are never edited. `tooling/babel-plugin-data-loc.cjs` is still the visitor it uses. Verified on iiitu-acm (Vite 8 / plugin-react 6): findings resolve to e.g. `src/components/Footer.jsx:90:9`.

- **Opacity diff extensions (`detect/pixels.py`):** collisions are tested both ways (hide A, hide B) since either may be on top; occlusion diffs the *full rectangles* of target and coverer (a banner's text box is nowhere near the button it covers); element protrusion measures paint in the part of the child outside its parent, because there is no overlap to diff.
- **`is_stacked` looks at ancestors:** a sticky or fixed ancestor marks a pair as stacked (hint for triage). Scroll-tiled captures always show a sticky nav overlapping scrolled content, e.g. iiitu-acm's `Layout.jsx:45` collides with footer links in the pixels but by design; Spark's "intentional" verdict is what dismisses those, so without the key they stay `confirmed`.

- **SAM is parsed without `meta-sam-parser`** (its install was refused in this environment). `meta/sam.py` builds prompts and parses records against the documented grammar; evidence is the box confidence and returned-bounds IoU. Occlusion is observable when SAM confidence < 0.8 (spike 1: clear 0.98, covered 0.42-0.61). Mask fill/spill is not computed, and `PixelEvidence.sam_spill` is bounds-based until masks are decoded.
- **Transient overlaps are dismissed by code** (`oracles.is_transient` -> `metrics["transient"]` -> `fuse.decide`): a fixed/sticky element over in-flow content the user can scroll apart is by design. Spark was inconsistent on these.
- **Candidates are kept only in tiles where their elements are on screen** (`oracles.on_screen`); the snapshot lists off-screen elements too. Contrast is placed in the first tile that shows the element.
- **Triage output is validated inside the cached call**, so an out-of-range answer is retried and never cached.
- **Key variable:** `MODEL_API_KEY`, or `META_MODEL_API` (the name this environment stores it under).

- **Fix edits are exact search/replace (`edit_file`), not model-written unified diffs.** Wonder needed four tries on a trivial fix because its hunk headers were wrong. The diff the linter and verifier see is always `git diff` of the worktree, so it is well-formed. Each edit is linted and reverted if blocked, so a blocked edit never stays in the tree.
- **Agent turns are stateless** (the whole transcript is sent each turn; Wonder accepts its own output items as input), so every turn goes through `call()` and is cached and replayable. The guide's `previous_response_id` would not be. Token counts include live calls only.
- **Worktrees live under Fixel's `.fixel/wt/<target>/`**, not inside the target repo (which would show up as untracked files there). `node_modules` is symlinked in; paths are confined to the app directory and never touch `node_modules` or `.git`.
- **`fix/lint.py` is stricter than the guide's**: it parses hunks by their counts (a removed line starting with `--` is not a header), also blocks truncation (`truncate`, ellipsis, line-clamp), collapsing (`w-0`, `width:0`, `scale(0)`), off-screen positioning, transparent text, `clip`/`clip-path`, `pointer-events: none` (defeats the hit test) and removing elements, and only treats a string as a class list inside a `className`/`clsx`-style context or when it is utility-shaped.
- **The verifier's line remap is exact** (old->new line map from each hunk's context, so elements on trailing context lines inside a hunk are remapped too; the guide only shifts lines after a hunk). Drift lets ancestors of the fixed region grow taller (their content grew) while still flagging sideways movement; the fix container is everything under the parent of the finding's nearest common ancestor.
- **Finding keys must be stable under small layout shifts.** An occlusion names its coverer by its fixed/sticky root (not the inner element a sample point hit), and a collision already explained by an occlusion is dropped. Without this the same cookie-banner defect appeared "new" after an unrelated patch and pushed the model into scope creep.
- **Oracle gaps found by tests:** text spilling out of a narrow box now counts as viewport protrusion; protruding siblings are reported once as their protruding parent.

## Build order and cut order

Protect a working scan-to-verified-fix loop first, then evidence, then extras (guide section 13). If behind, cut: synthetic corpus → explorer → voice intake → grounding chip. Never cut: the model-free verifier, the linter, the human-labelled benchmark, replay mode.
