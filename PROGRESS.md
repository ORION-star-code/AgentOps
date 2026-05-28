# Project Progress

## Current Status
- Project: AgentOps
- Latest checkpoint: F03 evaluation foundation complete
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

## In Progress
- None

## Blocked
- None recorded

## Next Steps
1. Start `F04` by defining regression comparison between baseline and candidate evaluation results.
2. Add prompt/model/version metadata required to compare Agent changes safely.
3. Keep WIP=1 and update `docs/features.json` with evidence after each passing verification.
