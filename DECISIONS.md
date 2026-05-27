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
