PYTHON ?= python

.PHONY: setup dev test lint harness-check check

setup:
	@echo "TODO: replace with project-specific dependency installation"

dev:
	@echo "TODO: replace with project-specific startup command"

test:
	$(PYTHON) -m unittest discover -s tests

lint:
	$(PYTHON) -m py_compile harness/validate.py

harness-check:
	$(PYTHON) harness/validate.py

check: lint test harness-check
