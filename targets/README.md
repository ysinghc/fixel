# targets

Demo target apps, kept as git submodules and never edited: Fixel injects its `data-loc` plugin through a wrapper
Vite config (`tooling/vite.config.fixel.mjs`). One config per target (`targets/<name>.yaml`).

| Target | Split | Stack | License |
|---|---|---|---|
| iiitu-acm (`client/`) | development | React 19, Vite 8, Tailwind 4, React Router | none (author's own code) |
| pastebin (`frontend/`) | development | React 19, Vite 8, Tailwind 4 | none (author's own code) |
| aavesh (`client/`) | test | React 19, Vite 6, Tailwind 3, three.js | GPL v2 (fork); pointer only |
| demo-shop | fix-loop demo and tests | React 19, Vite 8, Tailwind 4 | authored for Fixel; three planted defects |

A second test target is still to be chosen. Thresholds are tuned on the development split only; report
test-split numbers only (guide section 9.1).

```bash
make targets                                   # init submodules and npm install each app
fixel scan --config targets/iiitu-acm.yaml
```
