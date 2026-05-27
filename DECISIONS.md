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
