# AgentOps Architecture

## Product Boundary

AgentOps is a developer tool for inspecting, evaluating, and improving LangGraph and RAG Agent systems. It focuses on run observability, retrieval evidence, automated answer quality checks, and regression detection.

It is not a general chatbot runtime or an enterprise Agent orchestration platform.

## Initial Module Boundaries

- `agentops_api.api`: HTTP routes and request/response wiring.
- `agentops_api.observability`: Agent run traces, reasoning timeline, tool calls, token usage, latency, and errors.
- `agentops_api.rag`: Retrieval queries, chunks, citations, hit/miss signals, and grounding evidence.
- `agentops_api.evaluation`: Hallucination risk, groundedness, answer trustworthiness, and regression checks.

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
- `POST /v1/runs/{run_id}/events`
- `GET /v1/runs/{run_id}/events`

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

## Validation Boundary

Every implementation step must preserve:

- `python harness/validate.py`
- `python -m pytest`
- `python -m ruff check .`
- `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`
