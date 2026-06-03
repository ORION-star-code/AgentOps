# AgentOps Architecture

## Product Boundary

AgentOps is a developer tool for inspecting, evaluating, and improving LangGraph and RAG Agent systems. It focuses on run observability, retrieval evidence, automated answer quality checks, and regression detection.

It is not a general chatbot runtime or an enterprise Agent orchestration platform.

## Initial Module Boundaries

- `agentops_api.api`: HTTP routes and request/response wiring.
- `agentops_api.audit`: Non-sensitive security audit event contracts.
- `agentops_api.security`: API key authentication, scope checks, and project isolation.
- `agentops_api.privacy`: Sensitive JSON redaction and retention configuration.
- `agentops_api.observability`: Agent run traces, reasoning timeline, tool calls, token usage, latency, and errors.
- `agentops_api.rag`: Retrieval queries, chunks, citations, hit/miss signals, and grounding evidence.
- `agentops_api.evaluation`: Hallucination risk, groundedness, answer trustworthiness, and regression checks.
- `agentops_api.sdk`: Python client for developer ingestion and evaluation workflows.
- `agentops_api.instrumentation`: Framework-specific helpers built on top of the SDK.
- `agentops_api.viewer`: Minimal browser UI served by FastAPI and backed by authenticated `/v1` APIs.

## F06 Security Boundary

All `/v1` APIs require an `X-AgentOps-API-Key` header. API keys are configured as project-bound credentials with explicit scopes:

```json
[
  {
    "key_hash": "sha256:ed5a18fb8f807f996d649e379d3f35f39c543a91bdbf88c492f2ebd10d4df86c",
    "key_id": "local-dev",
    "project_id": "demo-project",
    "scopes": ["ingest", "read", "evaluate", "admin"],
    "revoked": false
  }
]
```

The server hashes the presented `X-AgentOps-API-Key` before comparing credentials. Plain `key` entries are still accepted for local development and tests, but they are normalized to `sha256:<hex>` in memory. `key_id` gives future audit logs a stable non-secret identifier, and `revoked: true` rejects a key without removing historical configuration.

### Authorization Rules

- `GET /health` is public.
- `ingest` can create runs, append timeline events, and write RAG evidence.
- `read` can fetch runs, timelines, and run detail.
- `evaluate` can write evaluation events and compare regression payloads.
- `admin` satisfies scope checks for its bound project, but does not bypass project isolation.
- Run-scoped APIs verify that the stored run `project_id` matches the authenticated API key project.
- Missing or invalid API keys return `401`; insufficient scope or cross-project access returns `403`.

## F18.2 Audit Log Boundary

Security-relevant `/v1` requests are recorded as non-sensitive audit rows in SQLite:

```text
HTTP /v1 request
        |
        v
auth dependency marks project_id, key_id, and required scope
        |
        v
audit middleware records outcome after response status is known
        |
        v
audit_events table
```

### Audit Event Contract

- `project_id`: authenticated project when available.
- `key_id`: configured non-secret API key identifier when available.
- `scope`: required API scope for the route.
- `method` and `path`: HTTP method and route path without query string.
- `status_code`, `outcome`, `reason`, and `timestamp`.

Audit events intentionally do not store request bodies, response bodies, query strings, or raw API keys. Missing-key and invalid-key requests are still audited, but without project or key context. Route-level failures such as cross-project access are recorded with the authenticated project/key context and a failed outcome.

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
- `GET /v1/runs/{run_id}/events?limit=100&after_sequence=0&type=tool_call`

## F09 Timeline Query Scalability

Timeline query APIs return bounded pages:

- `limit`: page size, default `100`, maximum `500`.
- `after_sequence`: cursor; returns events with sequence greater than this value.
- `type`: optional event type filter, such as `message`, `tool_call`, or `error`.

The event list endpoint returns events in ascending sequence order. Invalid limits return `422`.

Run detail returns a full run summary plus the latest 100 timeline events, also in ascending sequence order. This keeps the developer detail contract useful without forcing large runs to load every event into the response.

Full trace export remains a future explicit endpoint instead of being hidden behind the normal detail view.

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

- `EvaluationResult`: `answer`, evaluator/rubric/judge metadata, `rag_event_id`, `verdict`, `metrics`, `metadata`.
- Reproducibility fields: `evaluator_id`, `evaluator_version`, `rubric_id`, `rubric_version`, `judge_model`, and `threshold_profile`.
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
- `GET /v1/regressions/reports/{report_id}`

## F10 Evaluation And Regression Reproducibility

Evaluation records carry explicit evaluator and rubric identity so historical quality evidence can be interpreted after prompts, rules, and judge models change:

- `evaluator_id` and `evaluator_version` identify the deterministic evaluator or future judge runner.
- `rubric_id` and `rubric_version` identify the scoring rubric.
- `judge_model` identifies the model contract when an external judge is used.
- `threshold_profile` identifies the configured pass/fail threshold set.

Regression comparisons are persisted in SQLite as `regression_reports` rows. Each report stores:

- `id`, `project_id`, and `created_at`.
- Baseline and candidate run/version/prompt/model metadata.
- Baseline and candidate evaluator/rubric/judge/threshold metadata.
- Baseline and candidate verdicts.
- Metric-level score deltas, quality deltas, and improved/regressed flags.

The comparison endpoint returns the persisted report, and `GET /v1/regressions/reports/{report_id}` retrieves it later. Report reads enforce project access through the stored report `project_id`.

The golden dataset contract is schema-only in this sprint. It defines versioned deterministic cases with user input, reference context, expected tools, expected tool arguments, risk level, approval requirement, judge rubric, and pass criteria. Dataset runners and external LLM judges are future work.

## F11 Mimo LLM Judge Runner

Mimo is the first real external judge provider. It uses the OpenAI-compatible `/chat/completions` API and produces the same `EvaluationResult` payload that manual evaluations already store.

### Configuration

- `AGENTOPS_MIMO_API_KEY`: Mimo API key, required for live judge calls.
- `AGENTOPS_MIMO_BASE_URL`: defaults to `https://token-plan-cn.xiaomimimo.com/v1`.
- `AGENTOPS_MIMO_MODEL`: defaults to `mimo-v2.5-pro`.
- `AGENTOPS_MIMO_TIMEOUT_SECONDS`: defaults to `30`.
- `AGENTOPS_MIMO_MAX_RETRIES`: defaults to `1`.

Keys must stay in the environment and must not be committed to repository files.

### Current Mimo API

- `POST /v1/runs/{run_id}/evaluations/judge`

The endpoint requires `evaluate` scope, checks project ownership, rejects terminal runs before calling Mimo, asks Mimo for JSON-only metric scores, validates the returned metrics, and stores the result as a typed `evaluation` timeline event named `mimo_judge_evaluation`.

Live verification is intentionally separated from the default check path:

- Default validation uses mocked Mimo responses.
- `scripts/smoke-mimo.ps1` performs a live smoke only when `AGENTOPS_MIMO_API_KEY` is set.

## F12 Golden Dataset Runner

Golden dataset execution turns the F10 dataset contract into repeatable evaluation evidence. The API creates a normal Agent run for each dataset execution, writes one `evaluation` event per successfully evaluated case, writes one compact `custom` summary event, then marks the run as `succeeded`.

```text
GoldenDataset
        |
        v
POST /v1/golden-datasets/runs
        |
        v
AgentRun(name="Golden dataset: {dataset_id}@{version}")
        |
        v
RunEvent(type="evaluation", name="golden_dataset_case_evaluation")
        |
        v
RunEvent(type="custom", name="golden_dataset_summary")
```

### Current Dataset API

- `POST /v1/golden-datasets/runs`

The endpoint requires `evaluate` scope and checks that the request `project_id` matches the authenticated API key project. It returns aggregate counts plus ordered per-case results.

### Judge Modes

- `deterministic`: default local mode for repeatable tests and no-network validation.
- `mimo`: calls the configured Mimo provider explicitly and is tested through injected provider doubles in the default check path.

Individual case failures do not erase successful case evidence. A case without `expected_answer`, a provider failure, or a non-passing evaluation is represented in the per-case result and aggregate failure count while the dataset execution run still completes.

F12 intentionally does not add dataset tables. Querying uses the existing run detail and timeline APIs until longer-term dataset run analytics justify dedicated storage.

## F13 Golden Dataset Regression Pipeline

Golden dataset regression compares two completed F12 runs by reading their persisted `golden_dataset_case_evaluation` events and aligning cases by `metadata.case_id`.

```text
baseline GoldenDataset run      candidate GoldenDataset run
        |                               |
        v                               v
evaluation events by case_id     evaluation events by case_id
        \                               /
         v                             v
POST /v1/golden-datasets/regressions/compare
        |
        v
per-case RegressionReport rows + aggregate dataset verdict
```

### Current Dataset Regression API

- `POST /v1/golden-datasets/regressions/compare`

The endpoint requires `evaluate` scope and enforces project ownership on both run IDs. It rejects running runs with `409` and rejects non-dataset runs, mismatched datasets, mismatched case sets, duplicate case IDs, or invalid evaluation payloads with `422`.

### Persistence Strategy

F13 reuses the existing `regression_reports` table. Each comparable case produces one persisted `RegressionReport` with `metadata.agentops_kind = "golden_dataset_case_regression"` and a stable `case_id`. The API response aggregates those report IDs into a dataset-level verdict:

- `regressed` if any case report regressed.
- `improved` if no case regressed and at least one case improved.
- `unchanged` otherwise.

This keeps reports auditable through `GET /v1/regressions/reports/{report_id}` without adding aggregate dataset tables before UI and CI query patterns are clearer.

## F14 Python Ingestion SDK

The SDK is a thin synchronous wrapper around the HTTP API. It does not bypass authentication, project isolation, validation, redaction, or repository behavior; it only reduces integration friction for LangGraph and RAG developers.

```text
LangGraph/RAG application
        |
        v
AgentOpsClient
        |
        v
HTTP /v1 APIs with X-AgentOps-API-Key
        |
        v
existing API validation, security, redaction, and persistence
```

### SDK Boundary

- `AgentOpsClient` owns an `httpx.Client` by default.
- Tests and embedded integrations can inject a compatible HTTP client.
- API keys are sent as `X-AgentOps-API-Key` per request.
- The configured `project_id` is used as the default for project-scoped create/compare calls.
- Non-2xx responses raise `AgentOpsAPIError` with status code and API detail.

### Current SDK Coverage

The SDK covers:

- Run lifecycle: create, get, complete, fail, cancel, detail.
- Timeline events: append and list with pagination/filter parameters.
- RAG evidence ingestion.
- Manual and Mimo judge evaluation ingestion.
- Golden dataset execution.
- Golden dataset regression comparison.
- Regression report lookup.

The SDK stays synchronous in F14 because the local FastAPI/SQLite MVP and most LangGraph callback integrations can use blocking ingestion initially. Async, batching, retries, and background queues are deferred until ingestion volume justifies them.

## F15 LangGraph Instrumentation

F15 adds lightweight LangGraph-oriented helpers over `AgentOpsClient`. It does not depend on LangGraph directly; instead, it exposes context managers and wrappers that can be called from LangGraph nodes, callbacks, or fake graph tests.

```text
LangGraph node/callback
        |
        v
LangGraphInstrumentation / LangGraphRun
        |
        v
AgentOpsClient
        |
        v
existing /v1 trace APIs
```

### Captured Events

- `message`: `record_message(role, content)`.
- `tool_call`: `record_tool_call(tool_name, arguments, result, latency_ms, token_count)`.
- `model_call`: `record_model_call(model_name, prompt, response, latency_ms, token_count)`.
- `custom`: `run.node("node_name")` emits a `langgraph_node` event with status and latency.
- `error`: exceptions inside a node context emit `langgraph_error` and fail the run context.

### Lifecycle Rules

- `trace_run(...)` creates a normal AgentOps run with `agent_framework = "langgraph"`.
- Successful context exit completes the run.
- Exception exit records an error if needed, marks the run failed, and re-raises the original exception.
- `attach_run(run_id)` records into an existing run and leaves lifecycle ownership to the caller.

The helper is intentionally synchronous and dependency-light. A richer official LangGraph callback adapter can be added later without changing the stored event contract.

## F16 Trace Viewer UI

The first UI is a no-build browser shell served at `GET /viewer`. It is intentionally a debugging workspace, not a marketing page.

```text
Browser /viewer
        |
        | X-AgentOps-API-Key from session storage
        v
GET /v1/runs
        |
        v
GET /v1/runs/{run_id}/detail
```

### Viewer Boundary

- The viewer does not read SQLite directly and does not bypass API authentication.
- The API key is entered by the developer and stored only in `sessionStorage`.
- Run list data comes from `GET /v1/runs`, which is scoped to the authenticated project and requires `read`.
- `GET /v1/runs?include_summary=true` adds optional per-run aggregate summaries for event counts, typed event counts, token spend, and latency without changing the default lightweight response.
- Run detail data comes from `GET /v1/runs/{run_id}/detail`, preserving existing project ownership checks.
- The browser renders JSON payloads with text nodes so trace payloads are inspected as data, not executed as markup.
- The first version focuses on searchable run list, recent timeline page, compact event scanning, selected-event payload inspection, RAG evidence, evaluations, and errors.
- The UI remains framework-free until usage proves that larger frontend machinery is worth the maintenance cost.
- F16 front-end improvements are tracked as flat `F16.x` feature entries. F16.1 establishes a dark Agent Observatory visual system, F16.2 turns the event list into a Trace Spine, F16.3 structures the inspector, F16.4 adds optional project-scoped run summaries for the navigator, and F16.5 adds a collapsible SVG/CSS Trace Field mini map.
- WebGL remains deferred; the Trace Field is a lightweight overview layer that hides on mobile and reduced-motion contexts while the Trace Spine and Evidence Inspector remain the primary debugging surfaces.

### Current Viewer API

- `GET /viewer`
- `GET /v1/runs?limit=50&status=succeeded&include_summary=true`

## F17 Retention Cleanup

Retention cleanup uses `AGENTOPS_RETENTION_DAYS` to compute a cutoff and remove expired terminal run data from SQLite.

```text
scripts/retention.ps1 [-Execute]
        |
        v
python -m agentops_api.retention
        |
        v
TraceRepository.cleanup_expired_runs(dry_run=True|False)
        |
        v
DELETE terminal expired runs -> run_events cascade
```

### Cleanup Rules

- Retention is disabled by default when `AGENTOPS_RETENTION_DAYS` is unset.
- Dry-run is the default mode and returns JSON evidence without deleting data.
- Execute mode deletes only terminal runs with `ended_at` older than the cutoff.
- Running runs are never deleted, even when `started_at` is older than the cutoff.
- `run_events` are deleted through SQLite foreign-key cascade from the deleted runs.

### Current Cleanup Commands

- Dry-run: `powershell -ExecutionPolicy Bypass -File scripts/retention.ps1 -RetentionDays 30`
- Execute: `powershell -ExecutionPolicy Bypass -File scripts/retention.ps1 -RetentionDays 30 -Execute`

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
