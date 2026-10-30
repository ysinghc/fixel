# targets

Demo target apps, kept as git submodules and never edited: Fixel injects its `data-loc` plugin through a wrapper
Vite config (`tooling/vite.config.fixel.mjs`). One config per target (`targets/<name>.yaml`).

| Target | Split | Stack | License |
|---|---|---|---|
| iiitu-acm (`client/`) | development | React 19, Vite 8, Tailwind 4, React Router | none (author's own code) |
| pastebin (`frontend/`) | development | React 19, Vite 8, Tailwind 4 | none (author's own code) |
| aavesh (`client/`) | test | React 19, Vite 6, Tailwind 3, three.js | GPL v2 (fork); pointer only |
| e-broker (repo root) | test | Next.js 14 (App Router), React 18, Tailwind 3, TypeScript | MIT (author's own code); no data-loc, see below |
| demo-shop | fix-loop demo and tests | React 19, Vite 8, Tailwind 4 | authored for Fixel; three planted defects |

The test split is now `aavesh` and `e-broker`. Thresholds are tuned on the development split only; report
test-split numbers only (guide section 9.1).

```bash
make targets                                   # init submodules and npm install each app
fixel scan --config targets/iiitu-acm.yaml
```

## Notes per target

- **e-broker is not a Vite app.** Fixel's source-location plugin (`tooling/vite-plugin-data-loc.mjs`) only covers Vite, so e-broker findings are keyed by element fingerprint (`tag#text-hash`) rather than `file:line:col`, and `fixel fix` has no localized file set to start from (the agent would have to search). Only its public routes are scanned (`/`, `/recyclers`, `/scan`, `/auth/login`, `/auth/register`); the dashboard, vendor and admin areas need a login against its FastAPI backend, which is not run. Placeholder secrets in `targets/e-broker.yaml` let NextAuth start.
- **Nothing is tuned on the test split.** Run it for the benchmark's test numbers only; adjust thresholds and oracles on `iiitu-acm`, `pastebin` and `demo-shop`.
