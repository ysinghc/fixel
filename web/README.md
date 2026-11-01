# web

React + Vite + Tailwind UI. A Zustand store is fed by the API's server-sent event stream; every run page is a pure function of that
event log (`reduce` in `src/store.ts`), so reloading a page, opening an old run or replaying a recording rebuilds the same view.

```bash
make web          # npm ci + build into web/dist; `fixel serve` serves it at http://127.0.0.1:8765
make web-dev      # Vite dev server with hot reload, proxying /api to `fixel serve`
```

One task per page, each with its own URL (React Router). The page map, the four workflows and the 20 UX laws behind the layout are in
[`docs/UI_DESIGN.md`](../docs/UI_DESIGN.md).

| Page | URL | File |
|---|---|---|
| Home | `/` | `pages/Home.tsx` |
| New scan | `/scan` | `pages/ScanSetup.tsx` |
| Results | `/runs` | `pages/Runs.tsx` |
| A scan's findings | `/runs/:run` | `pages/RunPage.tsx` |
| Its screens | `/runs/:run/screens`, `/runs/:run/screens/:state` | `pages/ScreensPage.tsx`, `pages/ScreenPage.tsx` |
| One finding | `/runs/:run/findings/:key` | `pages/FindingPage.tsx` |
| A fix | `/runs/:run/fixes/:fix` | `pages/FixPage.tsx` |
| Label | `/label` | `pages/LabelPage.tsx` |
| Benchmark | `/benchmark` | `pages/BenchmarkPage.tsx` |

`layout/RunLayout.tsx` binds the store to the run in the URL and follows its event stream for every page under `/runs/:run`.
Keys: on a finding, `j`/`k` next/previous, `f` fix, `1`-`4` overlay layers, `Esc` back to the list; on Label, `v`/`n`/`u` and the arrows.

Browser tests: `tests/test_ui_e2e.py` (scan, finding, fix, refused fix, reload) and `tests/test_ui_bench_e2e.py` (blind labelling,
benchmark). Run `make web` and `make targets` first.
