"""FastAPI entrypoint for AgentOps."""

import os
from collections.abc import Iterable
from pathlib import Path

from fastapi import FastAPI

from agentops_api.api import router
from agentops_api.evaluation import MimoJudgeProvider, load_mimo_judge_config
from agentops_api.observability import DEFAULT_DB_PATH, TraceRepository
from agentops_api.privacy import load_retention_config
from agentops_api.security import ApiKeyCredential, ApiKeyStore, load_api_key_credentials


def create_app(
    db_path: str | Path | None = None,
    api_keys: Iterable[ApiKeyCredential] | None = None,
    mimo_judge_provider: MimoJudgeProvider | None = None,
) -> FastAPI:
    app = FastAPI(
        title="AgentOps",
        summary="Observability and automated evaluation for LangGraph and RAG Agents.",
        version="0.1.0",
    )
    retention_config = load_retention_config(os.getenv("AGENTOPS_RETENTION_DAYS"))
    app.state.retention_config = retention_config
    app.state.trace_repository = TraceRepository(
        db_path or DEFAULT_DB_PATH,
        retention_config=retention_config,
    )
    credentials = (
        list(api_keys)
        if api_keys is not None
        else load_api_key_credentials(os.getenv("AGENTOPS_API_KEYS"))
    )
    app.state.api_key_store = ApiKeyStore(credentials)
    app.state.mimo_judge_provider = mimo_judge_provider or MimoJudgeProvider(
        load_mimo_judge_config(),
    )
    app.include_router(router)

    return app


app = create_app()
