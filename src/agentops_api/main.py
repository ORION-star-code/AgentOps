"""FastAPI entrypoint for AgentOps."""

from pathlib import Path

from fastapi import FastAPI

from agentops_api.api import router
from agentops_api.observability import DEFAULT_DB_PATH, TraceRepository


def create_app(db_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(
        title="AgentOps",
        summary="Observability and automated evaluation for LangGraph and RAG Agents.",
        version="0.1.0",
    )
    app.state.trace_repository = TraceRepository(db_path or DEFAULT_DB_PATH)
    app.include_router(router)

    return app


app = create_app()
