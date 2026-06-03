# Sprint Contract: Production Readiness Sprint 1

## Scope
- Keep WIP=1 and advance only one production-readiness feature at a time.
- Current completed feature: F18.2 Audit Log.
- Current active branch sequence: production hardening.
- Next feature: F18.3 Rate Limiting.

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
- SDK features include API key/header checks, API error mapping, injected-client tests, and an integration test that writes a complete run lifecycle through public APIs.
- Instrumentation features include fake graph tests for node contexts, wrapper execution, model/tool usage, error capture, run completion/failure, and no real LangGraph dependency.
- UI features include API contract tests, authenticated data-access checks, project isolation checks, and a basic served-page test that proves credentials are not embedded in the shell.
- API key hardening features include hashed credential configuration, key identifier propagation, revoked key rejection, rotation tests, and no raw key persistence in credential objects.
- Audit log features include positive and negative security request coverage and must prove audit rows exclude raw API keys, request payloads, and query strings.
- F16 UI branch features are tracked as F16.x entries in `docs/features.json` so the Harness WIP=1 rule remains unchanged without adding nested feature schema.
- F16.5 keeps visual experimentation lightweight: SVG/CSS mini map first, WebGL deferred unless real debugging workflows need it.
- A fresh agent can answer what is complete, what is next, and how to verify from repository files alone.

## Exclusions
- Frontend build pipeline, routing framework, or chart library work until the no-build viewer proves real workflow needs.
- WebGL work is optional and deferred unless the lightweight Trace Field proves insufficient on real traces.
- Full enterprise auth, OAuth, or organization management.
- Large refactors unrelated to the active feature.
