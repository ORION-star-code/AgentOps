# Sprint Contract: Production Readiness Sprint 1

## Scope
- Keep WIP=1 and advance only one production-readiness feature at a time.
- Current completed feature: F08 trace ingestion correctness.
- Next feature: F09 timeline query scalability.

## Verification Standards
- `python harness/validate.py` passes.
- `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` passes, or blockers are written in `PROGRESS.md`.
- Security features include negative tests for missing API keys, invalid API keys, cross-project access, and insufficient scopes.
- Privacy features include tests proving sensitive values are not persisted and non-sensitive usage fields remain intact.
- Ingestion correctness features include tests for typed endpoint restrictions, lifecycle transitions, terminal write rejection, and concurrent sequence assignment.
- A fresh agent can answer what is complete, what is next, and how to verify from repository files alone.

## Exclusions
- UI and SDK work until security and ingestion foundations are stable.
- Full enterprise auth, OAuth, or organization management.
- Large refactors unrelated to the active feature.
