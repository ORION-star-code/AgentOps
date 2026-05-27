# Project Progress

## Current Status
- Project: AgentOps
- Latest checkpoint: F02 RAG evidence foundation complete
- Last validation: 2026-05-27, `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` passed
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

## In Progress
- None

## Blocked
- None recorded

## Next Steps
1. Start `F03` by defining automated answer quality evaluation results.
2. Connect groundedness, citation accuracy, hallucination risk, and trustworthiness checks to the existing run timeline.
3. Keep WIP=1 and update `docs/features.json` with evidence after each passing verification.
