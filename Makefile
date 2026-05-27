PYTHON ?= python

.PHONY: setup dev test lint harness-check check

setup:
	$(PYTHON) -m pip install -e ".[dev]"

dev:
	$(PYTHON) -m uvicorn agentops_api.main:app --reload --host 127.0.0.1 --port 8000

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

harness-check:
	$(PYTHON) harness/validate.py

check: lint test harness-check
