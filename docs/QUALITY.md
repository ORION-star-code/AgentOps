# Quality Notes

## AgentOps Foundation (Quality: B+)
- Verification passed: yes, `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`
- Agent understandable: yes, with AGENTS, progress, decisions, features, sprint contract, and architecture docs
- Test stability: schema and API coverage for trace, RAG evidence, evaluation, Mimo judge mocks, persisted regression reports, run detail, API key security, privacy redaction, ingestion correctness, timeline pagination, and golden dataset contracts
- Architecture boundaries: API, security, privacy, observability, RAG, evaluation, regression, and run detail contracts documented
- Code conventions: Ruff configured and passing

## Cleanup Priorities
1. Complete F11 live Mimo smoke with a rotated `AGENTOPS_MIMO_API_KEY`.
2. Add golden dataset execution on top of the Mimo judge provider.
3. Add PostgreSQL migration planning once SQLite MVP limits are reached.
4. Add background retention cleanup once a maintenance job boundary exists.
