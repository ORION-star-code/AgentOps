"""Top-level API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

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
    RunEvent,
    RunEventCreate,
    RunEventType,
    RunNotFoundError,
    TraceRepository,
)
from agentops_api.rag import RagEvidence

router = APIRouter()


def get_trace_repository(request: Request) -> TraceRepository:
    return request.app.state.trace_repository


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
) -> AgentRun:
    return repository.create_run(payload)


@router.get("/v1/runs/{run_id}", response_model=AgentRun)
def get_run(
    run_id: str,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
) -> AgentRun:
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post(
    "/v1/runs/{run_id}/events",
    response_model=RunEvent,
    status_code=status.HTTP_201_CREATED,
)
def append_run_event(
    run_id: str,
    payload: RunEventCreate,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
) -> RunEvent:
    try:
        return repository.append_event(run_id, payload)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc


@router.get("/v1/runs/{run_id}/events", response_model=list[RunEvent])
def list_run_events(
    run_id: str,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
) -> list[RunEvent]:
    try:
        return repository.list_events(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc


@router.post(
    "/v1/runs/{run_id}/rag/evidence",
    response_model=RunEvent,
    status_code=status.HTTP_201_CREATED,
)
def append_rag_evidence(
    run_id: str,
    evidence: RagEvidence,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
) -> RunEvent:
    payload = RunEventCreate(
        type=RunEventType.RAG_RETRIEVAL,
        name="rag_evidence",
        payload=evidence.model_dump(mode="json"),
    )
    try:
        return repository.append_event(run_id, payload)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc


@router.post(
    "/v1/runs/{run_id}/evaluations",
    response_model=RunEvent,
    status_code=status.HTTP_201_CREATED,
)
def append_evaluation_result(
    run_id: str,
    evaluation: EvaluationResultCreate,
    repository: Annotated[TraceRepository, Depends(get_trace_repository)],
) -> RunEvent:
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


@router.post("/v1/regressions/compare", response_model=RegressionReport)
def compare_regression(payload: RegressionComparisonCreate) -> RegressionReport:
    return build_regression_report(payload)
