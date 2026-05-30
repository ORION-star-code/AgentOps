# Project Progress

## Current Status
- Project: AgentOps
- Latest checkpoint: F16 Trace Viewer UI complete
- Last validation: 2026-05-30, `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` passed with Ruff, 135 pytest tests, and harness validation
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
- [x] F08 generic timeline endpoint now rejects `rag_retrieval` and `evaluation` event types
- [x] SQLite event sequence assignment now runs inside `BEGIN IMMEDIATE` with a busy timeout
- [x] Run lifecycle endpoints added: `/complete`, `/fail`, and `/cancel`
- [x] Terminal runs reject further timeline, RAG evidence, and evaluation writes
- [x] F09 timeline events query supports `limit`, `after_sequence`, and `type`
- [x] Timeline query defaults to 100 events and rejects limits above 500
- [x] Run detail now returns full run summary plus the latest 100 timeline events
- [x] F10 evaluation results now record evaluator, rubric, judge model, and threshold profile metadata
- [x] Versioned golden dataset schemas added for deterministic future evaluation suites
- [x] Regression comparison reports are persisted with report ID, project ID, creation time, verdicts, metric deltas, and reproducibility metadata
- [x] `/v1/regressions/reports/{report_id}` API added with project-scoped access checks
- [x] F11 Mimo judge provider implemented with OpenAI-compatible `/chat/completions`
- [x] Mimo configuration added through environment variables only
- [x] `/v1/runs/{run_id}/evaluations/judge` API added for platform-generated evaluation events
- [x] Mimo provider mock tests cover success, invalid JSON, missing metrics, invalid scores, timeout, API error, and missing API key
- [x] `scripts/smoke-mimo.ps1` added for live Mimo verification without storing secrets
- [x] F12 golden dataset runner implemented with deterministic default mode and explicit Mimo mode
- [x] `POST /v1/golden-datasets/runs` added with `evaluate` scope and project isolation
- [x] Dataset executions create normal Agent runs, per-case `evaluation` events, and a compact `custom` summary event
- [x] Per-case failures are returned without discarding successful evaluation evidence
- [x] Golden dataset schema, runner, API, auth, cross-project, partial failure, and provider injection tests passed
- [x] F13 golden dataset regression comparison implemented
- [x] `POST /v1/golden-datasets/regressions/compare` added with `evaluate` scope and project ownership checks
- [x] Completed golden dataset runs are aligned by `metadata.case_id`
- [x] Per-case regression reports are persisted through the existing `regression_reports` store
- [x] Dataset comparison returns aggregate improved, unchanged, and regressed counts
- [x] F13 tests cover auth, cross-project access, running run rejection, non-dataset rejection, mismatched cases, persisted report lookup, and deterministic regression detection
- [x] F14 synchronous Python `AgentOpsClient` implemented
- [x] SDK sends `X-AgentOps-API-Key` automatically and defaults project-scoped calls to configured `project_id`
- [x] SDK supports run lifecycle, timeline events, RAG evidence, manual evaluation, Mimo judge evaluation, golden dataset execution, dataset regression comparison, and regression report lookup
- [x] SDK errors map non-2xx responses to `AgentOpsAPIError` without exposing API keys
- [x] SDK tests cover mocked HTTP requests, error behavior, complete run lifecycle ingestion, and dataset regression integration
- [x] F15 lightweight LangGraph instrumentation helpers implemented
- [x] `LangGraphInstrumentation.trace_run` creates AgentOps runs and completes or fails them based on execution outcome
- [x] `LangGraphRun` records message, node, model call, tool call, custom, and error events through `AgentOpsClient`
- [x] Node contexts capture status and latency while preserving original exceptions
- [x] Fake graph tests cover successful node/model/tool capture, wrapped node execution, node error capture, failed run lifecycle, and attached existing runs
- [x] F16 project-scoped run list API added at `GET /v1/runs`
- [x] Trace Viewer UI added at `GET /viewer`
- [x] Viewer stores API keys only in browser session storage and calls authenticated `/v1` APIs
- [x] Viewer shows run list, selected run summary, recent timeline, RAG evidence, evaluations, and errors
- [x] F16 tests cover run list project isolation, status/limit filtering, read-scope enforcement, and credential-free viewer shell rendering

## In Progress
- None

## Blocked
- None recorded

## Next Steps
1. Start F17 Retention Cleanup.
2. Implement `AGENTOPS_RETENTION_DAYS` cleanup with dry-run and execute modes.
3. Protect active runs and verify expired trace deletion with temporary SQLite tests.
