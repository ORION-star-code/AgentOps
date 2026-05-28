# Quality Notes

## AgentOps Foundation (Quality: B+)
- Verification passed: yes, `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`
- Agent understandable: yes, with AGENTS, progress, decisions, features, sprint contract, and architecture docs
- Test stability: schema and API coverage for trace, RAG evidence, evaluation, regression comparison, and run detail
- Architecture boundaries: API, observability, RAG, evaluation, regression, and run detail contracts documented
- Code conventions: Ruff configured and passing

## Cleanup Priorities
1. Add authentication, project isolation, redaction, and retention controls before handling sensitive traces.
2. Add PostgreSQL migration planning once SQLite MVP limits are reached.
3. Add SDK/UI coverage on top of the stable API contracts.
