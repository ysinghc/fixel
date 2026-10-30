.PHONY: install targets test web web-dev serve demo-smoke

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

# Runs the demo path from the cache with the network off (guide section 14.1).
demo-smoke:
	FIXEL_MODE=replay pytest tests/test_demo_smoke.py
