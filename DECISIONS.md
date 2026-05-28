# Design Decisions

## 2026-05-27: Create a harness-first scaffold
- Decision: Initialize AgentOps with an agent-ready harness before feature work.
- Reason: Fresh agent sessions need durable context, validation commands, progress state, and task boundaries.
- Rejected alternatives: Start coding features from an empty directory without a documented bootstrap contract.
- Constraints: Keep WIP=1, define executable completion evidence, and keep project knowledge in versioned files.

## 2026-05-27: Initial stack
- Decision: Python 3.12, FastAPI, pytest, ruff, PowerShell command scripts
- Reason: Selected during project bootstrap; update this entry if the stack changes.
- Rejected alternatives: Not recorded yet.
- Constraints: Setup, dev, test, lint, and check commands must remain accurate.

## 2026-05-27: Use PowerShell scripts as canonical local commands
- Decision: Keep `scripts/setup.ps1`, `scripts/dev.ps1`, `scripts/test.ps1`, `scripts/lint.ps1`, and `scripts/check.ps1` as the primary command surface.
- Reason: The local Windows environment does not have `make`, while PowerShell is available and matches the user's workstation.
- Rejected alternatives: Require GNU Make for all contributors during the bootstrap phase.
- Constraints: `Makefile` may mirror the commands, but `AGENTS.md` must point to the PowerShell scripts first.

## 2026-05-27: Publish bootstrap checkpoints directly to main
- Decision: Use public repository `ORION-star-code/AgentOps` and push verified bootstrap checkpoints directly to `main`.
- Reason: The repository is new, the user requested GitHub commits after test stages, and direct main pushes keep the bootstrap history simple.
- Rejected alternatives: Draft PR for bootstrap, per-stage branches, or local-only commits.
- Constraints: Each pushed commit should correspond to a passing validation stage when network connectivity allows.

## 2026-05-27: Start observability with append-only trace events
- Decision: Model Agent observability as `AgentRun` plus ordered append-only `RunEvent` records.
- Reason: Agent debugging needs a durable timeline that can support tool calls, model calls, RAG retrieval, errors, evaluation, and custom events without separate incompatible stores.
- Rejected alternatives: Store only run summaries, or create separate tables for every event subtype before the event contract is stable.
- Constraints: Event payloads remain JSON objects capped at 64KB; future typed views can be derived from the event log.

## 2026-05-27: Use SQLite for MVP trace storage
- Decision: Persist local trace data in SQLite at `.agentops/agentops.db`.
- Reason: SQLite gives durable local debugging data without requiring a database service during MVP development.
- Rejected alternatives: In-memory storage because traces would disappear on restart; PostgreSQL first because it would add setup friction before schema shape is stable.
- Constraints: Keep repository boundaries narrow so PostgreSQL can replace SQLite later.

## 2026-05-27: Store RAG evidence as typed timeline events
- Decision: Persist RAG evidence through `RunEvent(type="rag_retrieval")` instead of creating dedicated RAG tables in F02.
- Reason: Retrieval evidence is part of the Agent execution timeline and should be visible alongside messages, model calls, tool calls, and errors.
- Rejected alternatives: Separate RAG persistence before query and evaluation patterns are stable.
- Constraints: RAG evidence must be validated before being written into the append-only event log.

## 2026-05-28: Store evaluation results as typed timeline events
- Decision: Persist answer quality evaluations through `RunEvent(type="evaluation")`.
- Reason: Evaluation results explain whether a specific answer in a specific run was grounded, cited, trustworthy, and low-risk, so they belong beside the trace and RAG evidence that produced the answer.
- Rejected alternatives: Dedicated evaluation tables before regression comparison requirements are clear.
- Constraints: Metric scores are normalized to `[0, 1]`; verdict computation remains deterministic until an external judge runner is added.

## 2026-05-28: Start regression comparison as a deterministic report
- Decision: Implement regression comparison as `POST /v1/regressions/compare` returning a `RegressionReport`, without persisting reports yet.
- Reason: The first production need is a stable comparison contract for prompt/model/code changes; persistence can be added after report shape and CI usage stabilize.
- Rejected alternatives: Store regression reports in SQLite immediately, or compare raw runs without normalized evaluation metrics.
- Constraints: Baseline and candidate must compare the same metric names and include version metadata.
