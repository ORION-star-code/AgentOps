# AgentOps

## Project Purpose
Developer observability and automated evaluation platform for LangGraph and RAG Agent systems.

## Stack
- Python 3.12, FastAPI, pytest, ruff, PowerShell command scripts

## Standard Commands
- Setup: `make setup`
- Dev server: `make dev`
- Test: `make test`
- Lint/static checks: `make lint`
- Complete validation: `make check`

## Hard Rules
- Keep WIP=1. Only one feature in `docs/features.json` may be `active`.
- A feature is `passing` only after its `verification` command succeeds.
- Update `PROGRESS.md` before ending a session.
- Record durable design choices in `DECISIONS.md`.
- Keep module-specific rules close to the module code.
- Do not start refactors or extra features until current validation evidence is recorded.

## Session Start
1. Read `PROGRESS.md`.
2. Read `DECISIONS.md`.
3. Read `docs/features.json`.
4. Run `make check` when practical.
5. Continue from the first `active` item, or choose one `not_started` item and mark only that item active.

## Session End
1. Update `PROGRESS.md`.
2. Update feature state and evidence in `docs/features.json`.
3. Run `make check` or record the exact blocker.
4. Leave clear next steps.

## Validation Levels
1. Syntax/static checks.
2. Unit tests.
3. Integration tests.
4. End-to-end or runtime checks for cross-component behavior.

## References
- `docs/features.json`: single source of truth for planned behavior.
- `docs/QUALITY.md`: quality and cleanup priorities.
- `docs/SPRINT_CONTRACT.md`: active task scope and acceptance criteria.
- `harness/validate.py`: mechanical harness checks.
