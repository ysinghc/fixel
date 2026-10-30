.PHONY: install targets test demo-smoke

install:
	pip install -e ".[dev]"
	npm ci
	playwright install chromium

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
