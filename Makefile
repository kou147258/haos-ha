# HAOS Dashboard — convenience targets.
# Windows users: run `python dev.py` directly (no make required).
# Unix users: `make dev` works as expected.

PYTHON ?= python3
PYTEST ?= pytest

.PHONY: dev test lint clean

dev:
	$(PYTHON) dev.py

test:
	$(PYTEST) tests/ -v

lint:
	$(PYTHON) -m compileall -q custom_components/haos haos_fb dev.py
	@echo "lint OK"

clean:
	rm -f dev-overview.png dev-page-*.png preview_*.png
	rm -rf .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true