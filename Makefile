.PHONY: install test demo-smoke

install:
	pip install -e ".[dev]"
	npm install
	playwright install chromium

test:
	pytest

# Runs the demo path from the cache with the network off (guide section 14.1).
demo-smoke:
	FIXEL_MODE=replay pytest tests/test_demo_smoke.py
