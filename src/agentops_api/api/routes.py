"""Top-level API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from agentops_api.evaluation import (
    EvaluationResultCreate,
    RegressionComparisonCreate,
    RegressionReport,
    build_evaluation_result,
    build_regression_report,
)
from agentops_api.observability import (
    AgentRun,
    AgentRunCreate,
    RunAlreadyEndedError,
    RunEvent,
    RunEventCreate,
    RunEventType,
    RunNotFoundError,
    RunDetail,
    TraceRepository,
    build_run_detail,
)
from agentops_api.rag import RagEvidence
from agentops_api.security import ApiKeyStore, ApiScope, AuthenticatedPrincipal

router = APIRouter()
API_KEY_HEADER = "X-AgentOps-API-Key"
GENERIC_EVENT_TYPES = {
    RunEventType.MESSAGE,
    RunEventType.MODEL_CALL,
    RunEventType.TOOL_CALL,
    RunEventType.ERROR,
    RunEventType.CUSTOM,
}


def get_trace_repository(request: Request) -> TraceRepository:
    return request.app.state.trace_repository


def get_api_key_store(request: Request) -> ApiKeyStore:
    return request.app.state.api_key_store


def require_scope(required_scope: ApiScope):
    def dependency(
        store: Annotated[ApiKeyStore, Depends(get_api_key_store)],
        api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
    ) -> AuthenticatedPrincipal:
        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key",
            )

        principal = store.authenticate(api_key)
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        if not principal.allows(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key does not have the required scope",
            )
        return principal

    return dependency


RequireIngest = Annotated[AuthenticatedPrincipal, Depends(require_scope(ApiScope.INGEST))]
RequireRead = Annotated[AuthenticatedPrincipal, Depends(require_scope(ApiScope.READ))]
RequireEvaluate = Annotated[AuthenticatedPrincipal, Depends(require_scope(ApiScope.EVALUATE))]


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "agentops-api",
    }


@router.post("/v1/runs", response_model=AgentRun, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: AgentRunCreate,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireIngest,
) -> AgentRun:
    _ensure_project_access(principal, payload.project_id)
    return repository.create_run(payload)


@router.get("/v1/runs/{run_id}", response_model=AgentRun)
def get_run(
    run_id: str,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireRead,
) -> AgentRun:
    return _get_authorized_run(repository, run_id, principal)


@router.post(
    "/v1/runs/{run_id}/events",
    response_model=RunEvent,
    status_code=status.HTTP_201_CREATED,
)
def append_run_event(
    run_id: str,
    payload: RunEventCreate,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireIngest,
) -> RunEvent:
    _ensure_generic_event_type(payload.type)
    _get_authorized_run(repository, run_id, principal)
    try:
        return repository.append_event(run_id, payload)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
    except RunAlreadyEndedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run has already ended",
        ) from exc


@router.get("/v1/runs/{run_id}/events", response_model=list[RunEvent])
def list_run_events(
    run_id: str,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireRead,
) -> list[RunEvent]:
    _get_authorized_run(repository, run_id, principal)
    try:
        return repository.list_events(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc


@router.get("/v1/runs/{run_id}/detail", response_model=RunDetail)
def get_run_detail(
    run_id: str,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireRead,
) -> RunDetail:
    run = _get_authorized_run(repository, run_id, principal)
    return build_run_detail(run, repository.list_events(run_id))


@router.post(
    "/v1/runs/{run_id}/rag/evidence",
    response_model=RunEvent,
    status_code=status.HTTP_201_CREATED,
)
def append_rag_evidence(
    run_id: str,
    evidence: RagEvidence,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireIngest,
) -> RunEvent:
    _get_authorized_run(repository, run_id, principal)
    payload = RunEventCreate(
        type=RunEventType.RAG_RETRIEVAL,
        name="rag_evidence",
        payload=evidence.model_dump(mode="json"),
    )
    try:
        return repository.append_event(run_id, payload)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
    except RunAlreadyEndedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run has already ended",
        ) from exc


@router.post(
    "/v1/runs/{run_id}/evaluations",
    response_model=RunEvent,
    status_code=status.HTTP_201_CREATED,
)
def append_evaluation_result(
    run_id: str,
    evaluation: EvaluationResultCreate,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireEvaluate,
) -> RunEvent:
    _get_authorized_run(repository, run_id, principal)
    result = build_evaluation_result(evaluation)
    payload = RunEventCreate(
        type=RunEventType.EVALUATION,
        name="answer_quality_evaluation",
        payload=result.model_dump(mode="json"),
    )
    try:
        return repository.append_event(run_id, payload)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
    except RunAlreadyEndedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run has already ended",
        ) from exc


@router.post("/v1/runs/{run_id}/complete", response_model=AgentRun)
def complete_run(
    run_id: str,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireIngest,
) -> AgentRun:
    _get_authorized_run(repository, run_id, principal)
    try:
        return repository.complete_run(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
    except RunAlreadyEndedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run has already ended",
        ) from exc


@router.post("/v1/runs/{run_id}/fail", response_model=AgentRun)
def fail_run(
    run_id: str,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireIngest,
) -> AgentRun:
    _get_authorized_run(repository, run_id, principal)
    try:
        return repository.fail_run(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
    except RunAlreadyEndedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run has already ended",
        ) from exc


@router.post("/v1/runs/{run_id}/cancel", response_model=AgentRun)
def cancel_run(
    run_id: str,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireIngest,
) -> AgentRun:
    _get_authorized_run(repository, run_id, principal)
    try:
        return repository.cancel_run(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
    except RunAlreadyEndedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run has already ended",
        ) from exc


@router.post("/v1/regressions/compare", response_model=RegressionReport)
def compare_regression(
    payload: RegressionComparisonCreate,
    principal: RequireEvaluate,
) -> RegressionReport:
    return build_regression_report(payload)


def _get_authorized_run(
    repository: TraceRepository,
    run_id: str,
    principal: AuthenticatedPrincipal,
) -> AgentRun:
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    _ensure_project_access(principal, run.project_id)
    return run


def _ensure_project_access(principal: AuthenticatedPrincipal, project_id: str) -> None:
    if principal.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key cannot access this project",
        )


def _ensure_generic_event_type(event_type: RunEventType) -> None:
    if event_type not in GENERIC_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Use the typed RAG or evaluation endpoint for this event type",
        )
