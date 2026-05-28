# AgentOps

AgentOps is a developer observability and automated evaluation platform for LangGraph and RAG Agent systems.

The project is focused on helping Agent developers inspect a task run end to end: reasoning steps, tool calls, token usage, failures, hallucination risk, RAG retrieval quality, answer trustworthiness, and regression after changes.

## Current Status

This repository has a working trace, RAG evidence, answer quality evaluation, regression comparison, and run detail foundation. The API can create Agent runs, append timeline events, record structured RAG retrieval evidence, persist evaluation results, compare candidate changes against baselines, and return a developer-facing run detail payload.

## Current API

- `GET /health`
- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/events`
- `GET /v1/runs/{run_id}/events`
- `POST /v1/runs/{run_id}/rag/evidence`
- `POST /v1/runs/{run_id}/evaluations`
- `POST /v1/regressions/compare`
- `GET /v1/runs/{run_id}/detail`

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
