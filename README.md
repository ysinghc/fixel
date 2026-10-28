# Fixel

Fixel finds visual layout bugs in a web app across a matrix of viewports, themes and text lengths, proves each one with pixels, traces it to the source line, and proposes a minimal CSS or className patch. A patch counts as fixed only after a deterministic, model-free verifier re-renders the whole matrix and finds the bug gone, nothing new broken, and nothing else moved.

> "Fixel" is a working title. **Status: early build.** Capture, the geometry oracles and a geometry-only `fixel scan` work; pixel evidence, triage, fixing and verification are still stubs (see `CLAUDE.md`).

## Docs

- [`docs/IMPLEMENTATION_GUIDE.md`](docs/IMPLEMENTATION_GUIDE.md): the full plan (architecture, code sketches, benchmark, UI, build schedule, risks). Items marked **[verify]** need checking in the first spike.
- [`CLAUDE.md`](CLAUDE.md): context and rules for Claude Code sessions in this repo.

## Layout

```
fixel.yaml        target, routes, matrix, budgets (draft)
backend/fixel/    Python backend: meta/, capture/, detect/, localize/, fix/, verify/, explore/, bench/, api/
tooling/          data-loc Babel plugin for source localization
web/              React demo UI (not scaffolded yet)
targets/          demo target apps (git submodules)
tests/            pytest + HTML fixtures
```

## Getting started

```bash
cp .env.example .env      # add MODEL_API_KEY
make install
make test
fixel scan --static tests/fixtures/site --route /index.html --widths 320 1440
```

`FIXEL_MODE` is `live`, `record` (default) or `replay`; replay serves every model call from the cache and spends nothing.
