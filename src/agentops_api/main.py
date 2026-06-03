"""FastAPI entrypoint for AgentOps."""

import os
from collections.abc import Iterable
from pathlib import Path

from fastapi import FastAPI, Request

from agentops_api.audit import AuditEvent, AuditOutcome
from agentops_api.api import router
from agentops_api.evaluation import MimoJudgeProvider, load_mimo_judge_config
from agentops_api.observability import DEFAULT_DB_PATH, TraceRepository
from agentops_api.privacy import load_retention_config
from agentops_api.security import ApiKeyCredential, ApiKeyStore, load_api_key_credentials
from agentops_api.viewer import router as viewer_router


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
    _install_audit_middleware(app)
    app.include_router(router)
    app.include_router(viewer_router)

    return app


def _install_audit_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def audit_v1_requests(request: Request, call_next):
        if not request.url.path.startswith("/v1"):
            return await call_next(request)

        try:
            response = await call_next(request)
        except Exception:
            _persist_audit_event(
                request,
                status_code=500,
                outcome=AuditOutcome.FAILED,
                reason="unhandled_exception",
            )
            raise

        reason = getattr(request.state, "agentops_audit_reason", None)
        if response.status_code >= 400:
            outcome = AuditOutcome.FAILED
            if reason in (None, "request_completed"):
                reason = "request_failed"
        else:
            outcome = AuditOutcome.SUCCEEDED
            reason = reason or "request_completed"

        _persist_audit_event(
            request,
            status_code=response.status_code,
            outcome=outcome,
            reason=reason,
        )
        return response


def _persist_audit_event(
    request: Request,
    *,
    status_code: int,
    outcome: AuditOutcome,
    reason: str,
) -> None:
    repository = getattr(request.app.state, "trace_repository", None)
    if repository is None:
        return

    event = AuditEvent(
        project_id=getattr(request.state, "agentops_audit_project_id", None),
        key_id=getattr(request.state, "agentops_audit_key_id", None),
        scope=getattr(request.state, "agentops_audit_scope", None),
        method=request.method,
        path=request.url.path,
        status_code=status_code,
        outcome=outcome,
        reason=reason,
    )
    try:
        repository.save_audit_event(event)
    except Exception:
        return


app = create_app()
