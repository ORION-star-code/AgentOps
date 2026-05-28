# Sprint Contract: Production Readiness Sprint 1

## Scope
- Keep WIP=1 and advance only one production-readiness feature at a time.
- Current completed feature: F06 security boundary and project isolation.
- Next feature: F07 redaction and retention controls for sensitive trace payloads.

## Verification Standards
- `python harness/validate.py` passes.
- `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` passes, or blockers are written in `PROGRESS.md`.
- Security features include negative tests for missing API keys, invalid API keys, cross-project access, and insufficient scopes.
- A fresh agent can answer what is complete, what is next, and how to verify from repository files alone.

## Exclusions
- UI and SDK work until security and ingestion foundations are stable.
- Full enterprise auth, OAuth, or organization management.
- Large refactors unrelated to the active feature.
