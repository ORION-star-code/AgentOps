# Quality Notes

## AgentOps Foundation (Quality: B+)
- Verification passed: yes, `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`
- Agent understandable: yes, with AGENTS, progress, decisions, features, sprint contract, and architecture docs
- Test stability: schema and API coverage for trace, RAG evidence, evaluation, regression comparison, run detail, and API key security
- Architecture boundaries: API, security, observability, RAG, evaluation, regression, and run detail contracts documented
- Code conventions: Ruff configured and passing

## Cleanup Priorities
1. Add redaction and retention controls before handling sensitive real-world traces.
2. Improve trace ingestion correctness with event type restrictions, sequence safety, and run lifecycle transitions.
3. Add PostgreSQL migration planning once SQLite MVP limits are reached.
4. Add SDK/UI coverage on top of the stable API contracts.
