# Sprint Contract: Production Readiness Sprint 1

## Scope
- Keep WIP=1 and advance only one production-readiness feature at a time.
- Current completed feature: F13 Regression Evaluation Pipeline.
- Next feature: F14 Python Ingestion SDK.

## Verification Standards
- `python harness/validate.py` passes.
- `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` passes, or blockers are written in `PROGRESS.md`.
- Security features include negative tests for missing API keys, invalid API keys, cross-project access, and insufficient scopes.
- Privacy features include tests proving sensitive values are not persisted and non-sensitive usage fields remain intact.
- Ingestion correctness features include tests for typed endpoint restrictions, lifecycle transitions, terminal write rejection, and concurrent sequence assignment.
- Query scalability features include tests for default limits, cursor progression, event type filtering, and invalid limit rejection.
- Reproducibility features include tests for versioned evaluator/rubric metadata, persisted reports, report lookup, negative access paths, and deterministic golden dataset contracts.
- External judge features include mock tests in the default check path and a separate live smoke script that never stores or prints provider API keys.
- Golden dataset features include deterministic no-network tests, provider-injection tests for external judge modes, per-case failure coverage, and run detail evidence checks.
- Golden dataset regression features include completed-run checks, project ownership checks, case alignment checks, persisted report lookup, and deterministic improved/unchanged/regressed coverage.
- A fresh agent can answer what is complete, what is next, and how to verify from repository files alone.

## Exclusions
- UI and SDK work until security and ingestion foundations are stable.
- Full enterprise auth, OAuth, or organization management.
- Large refactors unrelated to the active feature.
