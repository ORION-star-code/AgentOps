# AgentOps

AgentOps is a developer observability and automated evaluation platform for LangGraph and RAG Agent systems.

The project is focused on helping Agent developers inspect a task run end to end: reasoning steps, tool calls, token usage, failures, hallucination risk, RAG retrieval quality, answer trustworthiness, and regression after changes.

## Current Status

This repository has a working trace, RAG evidence, answer quality evaluation, regression comparison, run detail, API key security foundation, Mimo LLM-as-judge integration, golden dataset runner, and dataset regression pipeline. The API can create Agent runs, append timeline events, record structured RAG retrieval evidence, persist evaluation results, run repeatable golden datasets, compare candidate changes against baselines, persist reproducible regression reports, and return a developer-facing run detail payload.

All `/v1` endpoints require `X-AgentOps-API-Key`. Local credentials are configured with `AGENTOPS_API_KEYS`:

```powershell
$env:AGENTOPS_API_KEYS='[{"key":"local-dev-key","project_id":"demo-project","scopes":["ingest","read","evaluate","admin"]}]'
```

Mimo LLM-as-judge integration is configured with environment variables:

```powershell
$env:AGENTOPS_MIMO_API_KEY='<rotated-mimo-api-key>'
$env:AGENTOPS_MIMO_BASE_URL='https://token-plan-cn.xiaomimimo.com/v1'
$env:AGENTOPS_MIMO_MODEL='mimo-v2.5-pro'
```

Trace metadata and event payloads are redacted before persistence when sensitive field names such as `api_key`, `token`, `password`, `secret`, `authorization`, or `cookie` are found. Local retention defaults to indefinite; set `AGENTOPS_RETENTION_DAYS` to a positive integer to configure a retention window for future cleanup jobs.

## Current API

- `GET /health`
- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/complete`
- `POST /v1/runs/{run_id}/fail`
- `POST /v1/runs/{run_id}/cancel`
- `POST /v1/runs/{run_id}/events`
- `GET /v1/runs/{run_id}/events?limit=100&after_sequence=0&type=tool_call`
- `POST /v1/runs/{run_id}/rag/evidence`
- `POST /v1/runs/{run_id}/evaluations`
- `POST /v1/runs/{run_id}/evaluations/judge`
- `POST /v1/golden-datasets/runs`
- `POST /v1/golden-datasets/regressions/compare`
- `POST /v1/regressions/compare`
- `GET /v1/regressions/reports/{report_id}`
- `GET /v1/runs/{run_id}/detail`

Timeline queries default to 100 events and accept up to 500 events per page. Use `after_sequence` as a cursor and `type` to filter by event type. Run detail returns full summary counts plus the latest 100 timeline events.

Evaluation payloads include evaluator/rubric version metadata, judge model identity, and threshold profile. Regression comparisons are stored as project-scoped reports with ID, creation time, metric deltas, verdicts, and reproducibility metadata so results can be audited after the original request.

The Mimo judge endpoint calls the configured OpenAI-compatible Mimo model and persists its validated scores as a normal `evaluation` timeline event. Run `powershell -ExecutionPolicy Bypass -File scripts/smoke-mimo.ps1` after setting `AGENTOPS_MIMO_API_KEY` to perform a live smoke test.

Golden dataset execution defaults to a deterministic local judge so default validation never depends on network access or paid model quota. `judge_mode="mimo"` can reuse the configured Mimo provider when explicitly requested.

Golden dataset regression comparison reads completed dataset runs, aligns evaluation events by `case_id`, persists one regression report per comparable case, and returns an aggregate `improved`, `unchanged`, or `regressed` verdict.

## Project Documents

- `AGENTS.md`: agent landing page and workflow rules.
- `docs/features.json`: planned behavior and verification evidence.
- `PROGRESS.md`: current state and validation history.
- `DECISIONS.md`: durable technical decisions.
- `docs/QUALITY.md`: quality notes and cleanup priorities.
- `docs/ARCHITECTURE.md`: initial product and module boundaries.

## Local Commands

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
powershell -ExecutionPolicy Bypass -File scripts/test.ps1
powershell -ExecutionPolicy Bypass -File scripts/lint.ps1
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```
