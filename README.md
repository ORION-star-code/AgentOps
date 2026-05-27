# AgentOps

AgentOps is a developer observability and automated evaluation platform for LangGraph and RAG Agent systems.

The project is focused on helping Agent developers inspect a task run end to end: reasoning steps, tool calls, token usage, failures, hallucination risk, RAG retrieval quality, answer trustworthiness, and regression after changes.

## Current Status

This repository is in harness bootstrap. The first milestone is to make the project easy for a fresh coding agent to understand, run, validate, and continue safely.

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
