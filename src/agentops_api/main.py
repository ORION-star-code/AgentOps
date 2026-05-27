"""FastAPI entrypoint for AgentOps."""

from fastapi import FastAPI

from agentops_api.api import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentOps",
        summary="Observability and automated evaluation for LangGraph and RAG Agents.",
        version="0.1.0",
    )
    app.include_router(router)

    return app


app = create_app()
