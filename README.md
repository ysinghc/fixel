# Fixel

Fixel finds visual layout bugs in a web app across a matrix of viewports, themes and text lengths, proves each one with pixels, traces it to the source line, and proposes a minimal CSS or className patch. A patch counts as fixed only after a deterministic, model-free verifier re-renders the whole matrix and finds the bug gone, nothing new broken, and nothing else moved.

> "Fixel" is a working title. **Status: scan, fix and the demo UI work end to end.** `fixel scan` finds, confirms (geometry + opacity diff + SAM 3.1) and triages (Spark 1.3) layout defects on real apps and points at the source line. `fixel fix` repairs a finding in an isolated worktree and exports a patch only when a model-free verifier passes it. See `docs/SPIKES.md` for results and `CLAUDE.md` for status.

## Docs

- [`docs/IMPLEMENTATION_GUIDE.md`](docs/IMPLEMENTATION_GUIDE.md): the full plan (architecture, code sketches, benchmark, UI, build schedule, risks). Items marked **[verify]** need checking in the first spike.
- [`CLAUDE.md`](CLAUDE.md): context and rules for Claude Code sessions in this repo.

## Layout

```
fixel.yaml        target, routes, matrix, budgets (draft)
backend/fixel/    Python backend: meta/, capture/, detect/, localize/, fix/, verify/, explore/, bench/, api/
tooling/          data-loc Babel plugin for source localization
web/              React demo UI (served by `fixel serve` after `make web`)
targets/          demo target apps (git submodules)
tests/            pytest + HTML fixtures
```

## Getting started

```bash
cp .env.example .env      # add MODEL_API_KEY (META_MODEL_API also works)
make install
make test
fixel scan --static tests/fixtures/site --route /index.html --widths 320 1440   # add --offline to skip model calls
make targets && fixel scan --config targets/iiitu-acm.yaml
make serve                # API + demo UI at http://127.0.0.1:8765 (REST, SSE event stream, SQLite run history)
```

`FIXEL_MODE` is `live`, `record` (default) or `replay`; replay serves every model call from the cache and spends nothing.
