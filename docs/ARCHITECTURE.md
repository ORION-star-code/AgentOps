# AgentOps Architecture

## Product Boundary

AgentOps is a developer tool for inspecting, evaluating, and improving LangGraph and RAG Agent systems. It focuses on run observability, retrieval evidence, automated answer quality checks, and regression detection.

It is not a general chatbot runtime or an enterprise Agent orchestration platform.

## Initial Module Boundaries

- `agentops_api.api`: HTTP routes and request/response wiring.
- `agentops_api.security`: API key authentication, scope checks, and project isolation.
- `agentops_api.privacy`: Sensitive JSON redaction and retention configuration.
- `agentops_api.observability`: Agent run traces, reasoning timeline, tool calls, token usage, latency, and errors.
- `agentops_api.rag`: Retrieval queries, chunks, citations, hit/miss signals, and grounding evidence.
- `agentops_api.evaluation`: Hallucination risk, groundedness, answer trustworthiness, and regression checks.

## F06 Security Boundary

All `/v1` APIs require an `X-AgentOps-API-Key` header. API keys are configured as project-bound credentials with explicit scopes:

```json
[
  {
    "key": "local-dev-key",
    "project_id": "demo-project",
    "scopes": ["ingest", "read", "evaluate", "admin"]
  }
]
```

### Authorization Rules

- `GET /health` is public.
- `ingest` can create runs, append timeline events, and write RAG evidence.
- `read` can fetch runs, timelines, and run detail.
- `evaluate` can write evaluation events and compare regression payloads.
- `admin` satisfies scope checks for its bound project, but does not bypass project isolation.
- Run-scoped APIs verify that the stored run `project_id` matches the authenticated API key project.
- Missing or invalid API keys return `401`; insufficient scope or cross-project access returns `403`.

## F07 Privacy Boundary

Run metadata and event payloads are redacted before SQLite persistence. The repository applies one recursive redaction layer for every ingestion path, including generic timeline events, RAG evidence events, and evaluation events.

### Redaction Rules

- Default sensitive key names: `api_key`, `token`, `password`, `secret`, `authorization`, and `cookie`.
- Common suffix forms such as `access_token`, `client_secret`, and `user_password` are redacted.
- Non-sensitive usage fields such as `token_count` are preserved.
- Redacted values are replaced with `[REDACTED]`.
- Redaction evidence is added under `_agentops_redaction` with `redaction_count` and `redacted_fields`.
- This is an MVP field-name redactor, not a full DLP system.

### Retention Configuration

- Local trace retention defaults to indefinite.
- `AGENTOPS_RETENTION_DAYS` accepts a positive integer retention window.
- The configuration is loaded at app startup and stored on the app/repository boundary.
- Scheduled cleanup is intentionally deferred until a background job or maintenance command exists.

## F01 Trace Foundation

The first production data boundary is an append-only Agent run timeline:

```text
LangGraph/RAG Agent
        |
        | HTTP ingestion
        v
POST /v1/runs  ---->  runs table
        |
        v
POST /v1/runs/{run_id}/events  ---->  run_events table
        |
        v
GET /v1/runs/{run_id}/events  ---->  ordered timeline
```

### Data Contracts

- `AgentRun`: `id`, `project_id`, `session_id`, `name`, `status`, `started_at`, `ended_at`, `metadata`.
- `RunEvent`: `id`, `run_id`, `sequence`, `type`, `name`, `timestamp`, `payload`.
- `RunEvent.type`: `message`, `model_call`, `tool_call`, `rag_retrieval`, `error`, `evaluation`, `custom`.
- `metadata` and `payload` are JSON objects capped at 64KB.

### Storage Boundary

- SQLite is the MVP/local store at `.agentops/agentops.db`.
- `run_events` is append-only; the service does not expose event mutation endpoints.
- Event `sequence` is assigned server-side per run.
- The repository boundary should remain small enough to migrate to PostgreSQL later.

### Current API

- `GET /health`
- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/complete`
- `POST /v1/runs/{run_id}/fail`
- `POST /v1/runs/{run_id}/cancel`
- `POST /v1/runs/{run_id}/events`
- `GET /v1/runs/{run_id}/events`

## F08 Trace Ingestion Correctness

Generic timeline ingestion is restricted to low-level event types:

- `message`
- `model_call`
- `tool_call`
- `error`
- `custom`

RAG retrieval and evaluation events must be written through their typed endpoints so their domain validation cannot be bypassed.

### Lifecycle Rules

- New runs start as `running`.
- `POST /v1/runs/{run_id}/complete` transitions a run to `succeeded` and sets `ended_at`.
- `POST /v1/runs/{run_id}/fail` transitions a run to `failed` and sets `ended_at`.
- `POST /v1/runs/{run_id}/cancel` transitions a run to `canceled` and sets `ended_at`.
- Terminal runs reject further timeline, RAG evidence, and evaluation writes with `409`.
- Repeating a terminal transition also returns `409`.

### Sequence Correctness

SQLite event appends wrap the run status check, next sequence calculation, and insert in one `BEGIN IMMEDIATE` transaction. The connection uses a busy timeout so concurrent local writers wait for the write lock instead of racing on `MAX(sequence) + 1`.

## F02 RAG Evidence Foundation

RAG retrieval evidence is stored as a typed `rag_retrieval` event in the same run timeline:

```text
RAG Agent / retriever
        |
        v
POST /v1/runs/{run_id}/rag/evidence
        |
        v
RunEvent(type="rag_retrieval", payload=RagEvidence)
        |
        v
GET /v1/runs/{run_id}/events
```

### RAG Evidence Contract

- `RagEvidence`: `query`, `hit_status`, `chunks`, `citations`, `citation_coverage`, `metadata`.
- `RetrievedChunk`: `chunk_id`, `source_uri`, `content_preview`, `score`, `rerank_score`, `metadata`.
- `Citation`: `chunk_id`, `claim`, `quote`.
- `hit_status`: `hit`, `partial`, `miss`.

### RAG Validation Rules

- Citations must reference retrieved `chunk_id` values.
- `hit` evidence requires at least one retrieved chunk and at least one citation.
- `partial` evidence requires at least one retrieved chunk.
- `miss` evidence may have no chunks and cannot include citations.
- RAG evidence metadata uses the same 64KB JSON cap as trace metadata.

### Current RAG API

- `POST /v1/runs/{run_id}/rag/evidence`

## F03 Evaluation Foundation

Answer quality evaluation is stored as a typed `evaluation` event in the same run timeline:

```text
Evaluator / judge / deterministic check
        |
        v
POST /v1/runs/{run_id}/evaluations
        |
        v
RunEvent(type="evaluation", payload=EvaluationResult)
        |
        v
GET /v1/runs/{run_id}/events
```

### Evaluation Contract

- `EvaluationResult`: `answer`, `evaluator_name`, `rag_event_id`, `verdict`, `metrics`, `metadata`.
- `EvaluationMetric`: `name`, `score`, `threshold`, `direction`, `passed`, `rationale`.
- Metric names: `groundedness`, `citation_accuracy`, `hallucination_risk`, `trustworthiness`.
- Verdicts: `pass`, `warn`, `fail`.

### Evaluation Rules

- Scores and thresholds are normalized to the `[0, 1]` range.
- `groundedness`, `citation_accuracy`, and `trustworthiness` pass when score is greater than or equal to threshold.
- `hallucination_risk` passes when score is less than or equal to threshold.
- Metric names must be unique per evaluation result.
- Overall verdict is `pass` when all metrics pass, `fail` when no metrics pass, and `warn` for partial pass.

### Current Evaluation API

- `POST /v1/runs/{run_id}/evaluations`

## F04 Regression Foundation

Regression comparison is a deterministic API over two evaluation results:

```text
baseline EvaluationResult + candidate EvaluationResult
        |
        v
POST /v1/regressions/compare
        |
        v
RegressionReport(status, metric deltas, version metadata)
```

### Regression Contract

- `EvaluationComparisonSubject`: `run_id`, `version`, `prompt_version`, `model_version`, `evaluation`.
- `RegressionComparisonCreate`: `baseline`, `candidate`, `regression_tolerance`, `metadata`.
- `RegressionReport`: baseline/candidate run IDs and versions, baseline/candidate verdicts, status, tolerance, metric comparisons.
- `MetricRegressionComparison`: `name`, baseline/candidate scores, raw score delta, quality delta, threshold, and improved/regressed flags.

### Regression Rules

- Baseline and candidate must contain the same metric names.
- For `gte` metrics, higher candidate scores are better.
- For `lte` metrics, lower candidate scores are better.
- A metric regresses when quality delta is less than negative `regression_tolerance`.
- A metric improves when quality delta is greater than `regression_tolerance`.
- Report status is `regressed` if any metric regresses, `improved` if no metric regresses and at least one improves, otherwise `unchanged`.

### Current Regression API

- `POST /v1/regressions/compare`

## F05 Run Detail Contract

Run detail is a single developer-facing payload for inspecting one Agent execution:

```text
GET /v1/runs/{run_id}/detail
        |
        v
RunDetail(run, summary, timeline, typed event groups)
```

### Run Detail Contract

- `RunDetail`: `run`, `summary`, `timeline`, `messages`, `model_calls`, `tool_calls`, `rag_evidence`, `evaluations`, `errors`.
- `RunDetailSummary`: event counts by type plus total token and latency spend.
- The `timeline` remains ordered by server-assigned event `sequence`.
- Typed groups are views over the same timeline events, not separate persistence.

### Current Detail API

- `GET /v1/runs/{run_id}/detail`

## Validation Boundary

Every implementation step must preserve:

- `python harness/validate.py`
- `python -m pytest`
- `python -m ruff check .`
- `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`
