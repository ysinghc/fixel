# targets

Demo target apps, kept as git submodules and never edited: Fixel injects its `data-loc` plugin through a wrapper
Vite config (`tooling/vite.config.fixel.mjs`). One config per target (`targets/<name>.yaml`).

| Target | Split | Stack | License |
|---|---|---|---|
| iiitu-acm (`client/`) | development | React 19, Vite 8, Tailwind 4, React Router | none (author's own code) |
| pastebin (`frontend/`) | development | React 19, Vite 8, Tailwind 4 | none (author's own code) |
| aavesh (`client/`) | test | React 19, Vite 6, Tailwind 3, three.js | GPL v2 (fork); pointer only |
| e-broker (repo root) | test | Next.js 14 (App Router), React 18, Tailwind 3, TypeScript | MIT (author's own code); data-loc via the Next loader |
| demo-shop | fix-loop demo and tests | React 19, Vite 8, Tailwind 4 | authored for Fixel; three planted defects |

The test split is now `aavesh` and `e-broker`. Thresholds are tuned on the development split only; report
test-split numbers only (guide section 9.1).

```bash
make targets                                   # init submodules and npm install each app
fixel scan --config targets/iiitu-acm.yaml
```

## Notes per target

- **e-broker is not a Vite app**, so it gets its source locations from `tooling/next-data-loc.cjs` (a Node preload set through `NODE_OPTIONS`) and `tooling/next-data-loc-loader.cjs` (a webpack pre-loader), not the Vite plugin. The preload wraps Next's own config loader, so it works for `next.config.js`, `.mjs` and `.ts`, function and async configs, with no change to the repo. Dev only. Only its public routes are scanned (`/`, `/recyclers`, `/scan`, `/auth/login`, `/auth/register`); the dashboard, vendor and admin areas need a login against its FastAPI backend, which is not run. Placeholder secrets in `targets/e-broker.yaml` let NextAuth start.
- **Nothing is tuned on the test split.** Run it for the benchmark's test numbers only; adjust thresholds and oracles on `iiitu-acm`, `pastebin` and `demo-shop`.
