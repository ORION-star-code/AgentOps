# Project Progress

## Current Status
- Project: AgentOps
- Latest checkpoint: F07 redaction and retention configuration complete
- Last validation: 2026-05-28, `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` passed
- Current WIP: none

## Completed
- [x] Harness scaffold created on 2026-05-27
- [x] Public GitHub repository created at `ORION-star-code/AgentOps`
- [x] Minimal FastAPI application created with `GET /health`
- [x] PowerShell setup, dev, test, lint, and check scripts added
- [x] Initial module boundaries documented for API, observability, RAG, and evaluation
- [x] Bootstrap validation passed: Ruff, pytest smoke tests, and harness validator
- [x] F01 Agent run trace schemas added
- [x] SQLite append-only trace event repository added
- [x] `/v1/runs` and `/v1/runs/{run_id}/events` ingestion/query API added
- [x] Trace repository and API integration tests passed
- [x] F02 RAG evidence schemas added
- [x] RAG evidence validation rules added for chunks, citations, and hit status
- [x] `/v1/runs/{run_id}/rag/evidence` ingestion API added
- [x] RAG evidence is persisted as `rag_retrieval` timeline events
- [x] F03 evaluation result schemas added
- [x] Evaluation metric normalization and verdict computation added
- [x] `/v1/runs/{run_id}/evaluations` ingestion API added
- [x] Evaluation results are persisted as `evaluation` timeline events
- [x] F04 regression comparison schemas added
- [x] Regression comparison supports prompt/model/version metadata
- [x] `/v1/regressions/compare` API added
- [x] Regression reports classify improved, unchanged, and regressed candidates
- [x] F05 run detail schemas and summary builder added
- [x] `/v1/runs/{run_id}/detail` API added
- [x] Run detail aggregates ordered timeline, typed event groups, token spend, latency, and failures
- [x] F06 API key authentication added for all `/v1` routes
- [x] API keys are bound to project IDs and `ingest`, `read`, `evaluate`, or `admin` scopes
- [x] Run creation, run reads, timeline writes, RAG evidence writes, and evaluation writes enforce project ownership
- [x] Security tests cover missing keys, invalid keys, cross-project access, and insufficient scopes
- [x] F07 recursive JSON redaction added before SQLite persistence
- [x] Run metadata and event payload redaction evidence is recorded under `_agentops_redaction`
- [x] Default sensitive keys include `api_key`, `token`, `password`, `secret`, `authorization`, and `cookie`
- [x] `AGENTOPS_RETENTION_DAYS` configuration added with default indefinite local retention

## In Progress
- None

## Blocked
- None recorded

## Next Steps
1. Implement F08 trace ingestion correctness, including event type restrictions, sequence safety, and run lifecycle transitions.
2. Implement F09 timeline query scalability with limit, cursor, and event type filtering.
3. Add SDK/UI coverage only after the security and ingestion foundations are stable.
