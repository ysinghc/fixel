# Hosting Fixel at fixel.ysinghc.in

Fixel's backend drives Chromium, starts the target's dev server and makes git worktrees, so it needs a real machine (a VM
or container host), not serverless functions. The deployment is one container behind Caddy, which gets the HTTPS
certificate by itself. Files: `Dockerfile`, `deploy/docker-compose.yml`, `deploy/Caddyfile`.

## Steps

1. A Linux VM with Docker (2 vCPU / 4 GB is enough for one run at a time), ports 80 and 443 open.
2. DNS: an `A` record `fixel` → the VM's IP in the `ysinghc.in` zone (and `AAAA` if it has IPv6).
3. On the VM:
   ```bash
   git clone https://github.com/ysinghc/fixel.git && cd fixel
   cp .env.example .env    # set MODEL_API_KEY; never commit it
   cd deploy && docker compose up -d --build
   ```
4. Open https://fixel.ysinghc.in. `docker compose logs -f fixel` shows the limits it started with.

## What protects the Meta model API key (`backend/fixel/api/limits.py`, `tests/test_limits.py`)

Public mode (`FIXEL_PUBLIC=1` or `fixel serve --public`) turns on, all in code:

| Limit | Default | Variable |
|---|---|---|
| Model spend, whole server, per UTC day (persisted in `.fixel/spend.json`) | $5 | `FIXEL_DAILY_USD` |
| Model spend per scan or fix | $1 | `FIXEL_RUN_BUDGET_USD` |
| Full checks (SAM + Spark) per visitor IP per hour | 3 | `FIXEL_MODEL_SCANS_PER_HOUR` |
| Fix sessions per IP per hour | 2 | `FIXEL_FIXES_PER_HOUR` |
| Quick checks per IP per hour | 12 | `FIXEL_SCANS_PER_HOUR` |
| API requests per IP per minute | 240 | `FIXEL_RPM` |
| Scans and fixes running at once, server-wide | 1 | `FIXEL_MAX_ACTIVE_RUNS` |

When the daily cap is reached, running work stops starting model calls and new model work gets HTTP 429 with a
`Retry-After` until midnight UTC; quick checks (no models) keep working. Cached answers cost nothing and are not counted.
Public mode also refuses `base_url` scans (the server would fetch any address, including internal ones) and label writes
(the benchmark's ground truth comes only from the labeller's machine). Targets are limited to `FIXEL_CONFIG_ROOTS`
(the image sets the vendored demo-shop), so only synthetic or public code reaches the models, as `CLAUDE.md` requires.

The client IP is taken from `X-Forwarded-For` only with `FIXEL_TRUST_PROXY=1`; the compose file sets it because the
container is reachable only through Caddy, which overwrites that header with the real peer address. Do not set it on a
container that is reachable directly, or anyone can pick their own IP.

Add a hard monthly limit on the key itself in the Meta developer console as well: the code caps are the first line,
the provider's cap is the backstop.
