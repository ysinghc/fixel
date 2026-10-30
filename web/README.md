# web

React + Vite + Tailwind demo UI. A Zustand store is fed by the API's server-sent event stream; the screen is a pure function of that
event log (`reduce` in `src/store.ts`), so reloading the page, opening a past run, or replaying a recording rebuilds the same view.

```bash
make web          # npm ci + build into web/dist; `fixel serve` serves it at http://127.0.0.1:8765
make web-dev      # Vite dev server with hot reload, proxying /api to `fixel serve`
```

Views: **Scan** (state rail, stage with DOM/SAM/candidate/finding overlay layers and a width scrubber, findings panel, fix drawer) and
**Benchmark** (says plainly that it is not built yet; no number is shown until it is measured).
Keys: `j`/`k` next/previous finding, `f` fix the selected finding, `1`-`4` toggle overlay layers, `Esc` closes the drawer.

The browser test is `tests/test_ui_e2e.py` (run `make web` and `make targets` first).
