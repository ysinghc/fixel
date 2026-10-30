.PHONY: install targets test web web-dev serve bench-dev demo-smoke

install:
	pip install -e ".[dev]"
	npm ci
	playwright install chromium

# Build the React UI into web/dist, which `fixel serve` then serves next to the API.
web:
	cd web && npm ci && npm run build

# UI dev server with hot reload; proxies /api to `fixel serve` on 127.0.0.1:8765.
web-dev:
	cd web && npm run dev

serve: web
	fixel serve

targets:
	git submodule update --init --depth 1
	cd targets/iiitu-acm/client && npm ci
	cd targets/pastebin/frontend && npm ci
	cd targets/aavesh/client && npm ci
	cd targets/e-broker && npm ci
	cd targets/demo-shop && npm ci

test:
	pytest

# Benchmark on the development split (tuning only; never a result). The test split is run once, then labelled in the UI:
#   fixel bench run --split test --mutated 150 --clean 50 ; make serve ; label in the Label tab ; fixel bench export <run>
bench-dev:
	fixel bench run --split dev --mutated 60 --clean 20

# Runs the demo path from the cache with the network off (guide section 14.1).
demo-smoke:
	FIXEL_MODE=replay pytest tests/test_demo_smoke.py
