"""Top-level API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from agentops_api.evaluation import (
    EvaluationJudgeCreate,
    EvaluationResultCreate,
    GoldenDatasetRegressionCompareCreate,
    GoldenDatasetRegressionInputError,
    GoldenDatasetRegressionResult,
    GoldenDatasetRunCreate,
    GoldenDatasetRunNotCompleteError,
    GoldenDatasetRunResult,
    MimoJudgeAPIError,
    MimoJudgeNotConfiguredError,
    MimoJudgeProvider,
    MimoJudgeResponseError,
    MimoJudgeTimeoutError,
    RegressionComparisonCreate,
    RegressionReport,
    build_evaluation_result,
    build_regression_report,
    compare_golden_dataset_runs,
    run_golden_dataset,
)
from agentops_api.observability import (
    AgentRun,
    AgentRunCreate,
    AgentRunListItem,
    RunAlreadyEndedError,
    RunEvent,
    RunEventCreate,
    RunEventType,
    RunNotFoundError,
    RunDetail,
    RunStatus,
    TraceRepository,
    build_run_detail,
)
from agentops_api.rag import RagEvidence
from agentops_api.rate_limit import FixedWindowRateLimiter
from agentops_api.security import ApiKeyStore, ApiScope, AuthenticatedPrincipal

router = APIRouter()
API_KEY_HEADER = "X-AgentOps-API-Key"
DEFAULT_EVENT_LIMIT = 100
MAX_EVENT_LIMIT = 500
DEFAULT_RUN_LIMIT = 50
MAX_RUN_LIMIT = 100
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


def get_mimo_judge_provider(request: Request) -> MimoJudgeProvider:
    return request.app.state.mimo_judge_provider


def get_rate_limiter(request: Request) -> FixedWindowRateLimiter:
    return request.app.state.rate_limiter


def require_scope(required_scope: ApiScope):
    def dependency(
        request: Request,
        store: Annotated[ApiKeyStore, Depends(get_api_key_store)],
        rate_limiter: Annotated[FixedWindowRateLimiter, Depends(get_rate_limiter)],
        api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
    ) -> AuthenticatedPrincipal:
        request.state.agentops_audit_scope = required_scope.value
        if api_key is None:
            request.state.agentops_audit_reason = "missing_api_key"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key",
            )

        principal = store.authenticate(api_key)
        if principal is None:
            request.state.agentops_audit_reason = "invalid_api_key"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        request.state.agentops_audit_project_id = principal.project_id
        request.state.agentops_audit_key_id = principal.key_id
        _enforce_rate_limit(request, rate_limiter, principal)
        if not principal.allows(required_scope):
            request.state.agentops_audit_reason = "insufficient_scope"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key does not have the required scope",
            )
        request.state.agentops_audit_reason = "request_completed"
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


@router.get(
    "/v1/runs",
    response_model=list[AgentRunListItem],
    response_model_exclude_none=True,
)
def list_runs(
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireRead,
    limit: Annotated[int, Query(ge=1, le=MAX_RUN_LIMIT)] = DEFAULT_RUN_LIMIT,
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
    include_summary: bool = False,
) -> list[AgentRunListItem]:
    if include_summary:
        return repository.list_runs_with_summaries(
            principal.project_id,
            limit=limit,
            status=run_status,
        )
    return [
        AgentRunListItem(**run.model_dump())
        for run in repository.list_runs(principal.project_id, limit=limit, status=run_status)
    ]


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
    limit: Annotated[int, Query(ge=1, le=MAX_EVENT_LIMIT)] = DEFAULT_EVENT_LIMIT,
    after_sequence: Annotated[int | None, Query(ge=0)] = None,
    event_type: Annotated[RunEventType | None, Query(alias="type")] = None,
) -> list[RunEvent]:
    _get_authorized_run(repository, run_id, principal)
    try:
        return repository.list_events(
            run_id,
            limit=limit,
            after_sequence=after_sequence,
            event_type=event_type,
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc


@router.get("/v1/runs/{run_id}/detail", response_model=RunDetail)
def get_run_detail(
    run_id: str,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireRead,
) -> RunDetail:
    run = _get_authorized_run(repository, run_id, principal)
    summary = repository.get_event_summary(run_id)
    timeline = repository.list_recent_events(run_id, limit=DEFAULT_EVENT_LIMIT)
    return build_run_detail(run, timeline, summary=summary)


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


@router.post(
    "/v1/runs/{run_id}/evaluations/judge",
    response_model=RunEvent,
    status_code=status.HTTP_201_CREATED,
)
def append_judge_evaluation_result(
    run_id: str,
    evaluation: EvaluationJudgeCreate,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    judge_provider: Annotated[MimoJudgeProvider, Depends(get_mimo_judge_provider)],
    principal: RequireEvaluate,
) -> RunEvent:
    run = _get_authorized_run(repository, run_id, principal)
    _ensure_run_accepts_write(run)
    try:
        judged_evaluation = judge_provider.evaluate(evaluation)
    except MimoJudgeNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mimo judge API key is not configured",
        ) from exc
    except MimoJudgeTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Mimo judge request timed out",
        ) from exc
    except (MimoJudgeAPIError, MimoJudgeResponseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Mimo judge request failed",
        ) from exc

    result = build_evaluation_result(judged_evaluation)
    payload = RunEventCreate(
        type=RunEventType.EVALUATION,
        name="mimo_judge_evaluation",
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


@router.post(
    "/v1/golden-datasets/runs",
    response_model=GoldenDatasetRunResult,
    status_code=status.HTTP_201_CREATED,
)
def create_golden_dataset_run(
    payload: GoldenDatasetRunCreate,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    judge_provider: Annotated[MimoJudgeProvider, Depends(get_mimo_judge_provider)],
    principal: RequireEvaluate,
) -> GoldenDatasetRunResult:
    _ensure_project_access(principal, payload.project_id)
    return run_golden_dataset(
        payload,
        repository=repository,
        judge_provider=judge_provider,
    )


@router.post(
    "/v1/golden-datasets/regressions/compare",
    response_model=GoldenDatasetRegressionResult,
)
def compare_golden_dataset_regression(
    payload: GoldenDatasetRegressionCompareCreate,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireEvaluate,
) -> GoldenDatasetRegressionResult:
    _ensure_project_access(principal, payload.project_id)
    baseline_run = _get_authorized_run(repository, payload.baseline_run_id, principal)
    candidate_run = _get_authorized_run(repository, payload.candidate_run_id, principal)
    try:
        return compare_golden_dataset_runs(
            payload,
            repository=repository,
            baseline_run=baseline_run,
            candidate_run=candidate_run,
            project_id=principal.project_id,
        )
    except GoldenDatasetRunNotCompleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except GoldenDatasetRegressionInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
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
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireEvaluate,
) -> RegressionReport:
    report = build_regression_report(payload, project_id=principal.project_id)
    return repository.save_regression_report(report)


@router.get("/v1/regressions/reports/{report_id}", response_model=RegressionReport)
def get_regression_report(
    report_id: str,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    principal: RequireEvaluate,
) -> RegressionReport:
    report = repository.get_regression_report(report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regression report not found")
    _ensure_project_access(principal, report.project_id)
    return report


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


def _enforce_rate_limit(
    request: Request,
    rate_limiter: FixedWindowRateLimiter,
    principal: AuthenticatedPrincipal,
) -> None:
    decision = rate_limiter.check(principal.rate_limit_id)
    if decision.allowed:
        return

    request.state.agentops_audit_reason = "rate_limited"
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded",
        headers={
            "Retry-After": str(decision.reset_after_seconds),
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": str(decision.remaining),
        },
    )


def _ensure_run_accepts_write(run: AgentRun) -> None:
    if run.status != RunStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run has already ended",
        )


def _ensure_generic_event_type(event_type: RunEventType) -> None:
    if event_type not in GENERIC_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Use the typed RAG or evaluation endpoint for this event type",
        )
