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

## 2026-05-28: Build run detail as a derived view over the event log
- Decision: Implement `GET /v1/runs/{run_id}/detail` as an aggregated view over `AgentRun` and ordered `RunEvent` records.
- Reason: The UI and debugging workflow need one stable payload showing what happened, what tools were called, what was retrieved, how quality was judged, what was spent, and where failures occurred.
- Rejected alternatives: Persist a separate run detail snapshot that could drift from the append-only timeline.
- Constraints: Run detail remains derived from canonical events; future UI should consume this contract rather than querying multiple low-level endpoints.

## 2026-05-28: Protect `/v1` APIs with project-bound API keys
- Decision: Require `X-AgentOps-API-Key` for every `/v1` endpoint and bind each key to one `project_id` plus explicit scopes: `ingest`, `read`, `evaluate`, or `admin`.
- Reason: Agent traces, tool payloads, RAG evidence, and evaluation results can contain sensitive data, so the API needs a concrete security boundary before SDK or UI expansion.
- Rejected alternatives: Leave `/v1` unauthenticated during MVP, add a global development bypass, or let tests silently skip authentication.
- Constraints: `GET /health` remains public; `admin` satisfies scope checks but does not bypass project isolation; local credentials are configured through `AGENTOPS_API_KEYS` or explicit test injection.

## 2026-05-28: Redact sensitive JSON fields before SQLite persistence
- Decision: Apply recursive field-name based redaction to run metadata and event payloads in the repository before writing SQLite rows.
- Reason: Trace payloads can contain secrets from Agent tools, headers, retrievers, or evaluator metadata; a write-before-persist boundary protects every ingestion path consistently.
- Rejected alternatives: Redact only at API response time, rely on clients to remove secrets, or implement full DLP before the MVP store is stable.
- Constraints: This is a rule-based MVP redactor, not full DLP; redaction evidence is stored under `_agentops_redaction`; `AGENTOPS_RETENTION_DAYS` defines retention configuration, while scheduled cleanup is deferred until background job infrastructure exists.

## 2026-05-28: Harden trace ingestion before scaling timeline queries
- Decision: Restrict the generic event endpoint to low-level timeline events, require typed endpoints for RAG and evaluation writes, and make run lifecycle terminal through explicit complete/fail/cancel transitions.
- Reason: Typed RAG and evaluation payloads need their own validation, and finished Agent runs should be immutable for ordinary ingestion.
- Rejected alternatives: Let clients send all event types through `/events`, auto-finish runs from error events, or allow silent writes after terminal status.
- Constraints: SQLite sequence assignment uses `BEGIN IMMEDIATE` and busy timeout for MVP concurrency; terminal writes return `409`; future admin repair flows can be added explicitly instead of hidden bypasses.

## 2026-05-28: Page timeline APIs before adding UI scale
- Decision: Make `GET /v1/runs/{run_id}/events` return a bounded page by default, with `limit`, `after_sequence`, and `type` controls; make run detail return a full summary plus the latest 100 timeline events.
- Reason: Agent runs can produce large traces, and UI/API consumers need stable pages instead of unbounded timeline payloads.
- Rejected alternatives: Keep returning all events, use offset pagination, or make run detail omit full summary counts.
- Constraints: The default event page is 100, max page size is 500, cursor pagination uses server-assigned `sequence`, and full export remains a future explicit endpoint.

## 2026-05-29: Make evaluation and regression evidence reproducible
- Decision: Add evaluator, rubric, judge model, and threshold profile metadata to evaluation results, and persist regression comparison reports in SQLite with a report ID, project ID, creation time, verdicts, metric deltas, and the same reproducibility metadata.
- Reason: "Did this change get worse?" must be auditable after the API call returns, and historical evaluations need to show which evaluator/rubric/judge contract produced them.
- Rejected alternatives: Keep regression reports as transient responses only, infer evaluator versions from free-form metadata, or connect a real LLM judge before the deterministic contract is stable.
- Constraints: Regression report reads are project-scoped through the stored `project_id`; the golden dataset format is schema-only for now; real judge execution and dataset runners remain future work.
