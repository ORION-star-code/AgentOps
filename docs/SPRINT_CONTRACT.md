# Sprint Contract: Bootstrap AgentOps

## Scope
- Establish agent landing page, progress, decisions, feature inventory, validation, and quality notes.
- Add real setup, dev, test, lint, and check commands for the chosen stack.
- Add at least one smoke test.

## Verification Standards
- `python harness/validate.py` passes.
- `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` passes, or blockers are written in `PROGRESS.md`.
- A fresh agent can answer how to run, how to test, and what to do next from repository files alone.

## Exclusions
- Business feature implementation beyond smoke tests.
- Large refactors unrelated to bootstrap readiness.
