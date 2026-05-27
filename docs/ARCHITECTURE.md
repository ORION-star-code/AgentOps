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

## Validation Boundary

Every implementation step must preserve:

- `python harness/validate.py`
- `python -m pytest`
- `python -m ruff check .`
- `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`
