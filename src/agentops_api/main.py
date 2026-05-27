"""FastAPI entrypoint for AgentOps."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentOps",
        summary="Observability and automated evaluation for LangGraph and RAG Agents.",
        version="0.1.0",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "agentops-api",
        }

    return app


app = create_app()

