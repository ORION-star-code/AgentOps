"""Golden dataset regression comparison service."""

from __future__ import annotations

from agentops_api.evaluation.dataset_runner import CASE_EVALUATION_EVENT_NAME
from agentops_api.evaluation.schemas import (
    EvaluationMetricInput,
    EvaluationResult,
    EvaluationResultCreate,
    EvaluationComparisonSubject,
    GoldenDatasetCaseRegressionReport,
    GoldenDatasetRegressionCompareCreate,
    GoldenDatasetRegressionResult,
    RegressionComparisonCreate,
    RegressionReport,
    RegressionStatus,
    build_regression_report,
)
from agentops_api.observability import AgentRun, RunEvent, RunEventType, RunStatus, TraceRepository


class GoldenDatasetRegressionInputError(ValueError):
    """Raised when dataset runs cannot be compared."""


class GoldenDatasetRunNotCompleteError(RuntimeError):
    """Raised when a dataset run is still mutable."""


def compare_golden_dataset_runs(
    payload: GoldenDatasetRegressionCompareCreate,
    *,
    repository: TraceRepository,
    baseline_run: AgentRun,
    candidate_run: AgentRun,
    project_id: str,
) -> GoldenDatasetRegressionResult:
    """Compare matching case evaluations from two completed golden dataset runs."""

    _ensure_completed_golden_run(baseline_run, role="baseline")
    _ensure_completed_golden_run(candidate_run, role="candidate")
    dataset_id = _require_matching_dataset_id(baseline_run, candidate_run)
    baseline_evaluations = _load_case_evaluations(repository, baseline_run.id, role="baseline")
    candidate_evaluations = _load_case_evaluations(repository, candidate_run.id, role="candidate")
    _ensure_matching_case_ids(baseline_evaluations, candidate_evaluations)

    case_reports = [
        _compare_case(
            payload,
            project_id=project_id,
            case_id=case_id,
            baseline=baseline_evaluations[case_id],
            candidate=candidate_evaluations[case_id],
            repository=repository,
        )
        for case_id in sorted(baseline_evaluations)
    ]
    regressed_cases = sum(1 for report in case_reports if report.status == RegressionStatus.REGRESSED)
    improved_cases = sum(1 for report in case_reports if report.status == RegressionStatus.IMPROVED)
    unchanged_cases = sum(1 for report in case_reports if report.status == RegressionStatus.UNCHANGED)
    if regressed_cases:
        status = RegressionStatus.REGRESSED
    elif improved_cases:
        status = RegressionStatus.IMPROVED
    else:
        status = RegressionStatus.UNCHANGED

    return GoldenDatasetRegressionResult(
        project_id=project_id,
        baseline_run_id=baseline_run.id,
        candidate_run_id=candidate_run.id,
        dataset_id=dataset_id,
        baseline_dataset_version=str(baseline_run.metadata["dataset_version"]),
        candidate_dataset_version=str(candidate_run.metadata["dataset_version"]),
        status=status,
        regression_tolerance=payload.regression_tolerance,
        total_cases=len(case_reports),
        improved_cases=improved_cases,
        unchanged_cases=unchanged_cases,
        regressed_cases=regressed_cases,
        case_reports=case_reports,
        metadata=payload.metadata,
    )


def _ensure_completed_golden_run(run: AgentRun, *, role: str) -> None:
    if run.status == RunStatus.RUNNING:
        raise GoldenDatasetRunNotCompleteError(
            f"{role} golden dataset run must be complete before comparison"
        )
    if run.metadata.get("agentops_kind") != "golden_dataset_run":
        raise GoldenDatasetRegressionInputError(
            f"{role}_run_id must reference a golden dataset run"
        )
    if not run.metadata.get("dataset_id") or not run.metadata.get("dataset_version"):
        raise GoldenDatasetRegressionInputError(
            f"{role} golden dataset run is missing dataset metadata"
        )


def _require_matching_dataset_id(baseline_run: AgentRun, candidate_run: AgentRun) -> str:
    baseline_dataset_id = str(baseline_run.metadata["dataset_id"])
    candidate_dataset_id = str(candidate_run.metadata["dataset_id"])
    if baseline_dataset_id != candidate_dataset_id:
        raise GoldenDatasetRegressionInputError("baseline and candidate dataset_id values differ")
    return baseline_dataset_id


def _load_case_evaluations(
    repository: TraceRepository,
    run_id: str,
    *,
    role: str,
) -> dict[str, EvaluationResult]:
    events = repository.list_events(run_id, event_type=RunEventType.EVALUATION)
    case_events = [event for event in events if event.name == CASE_EVALUATION_EVENT_NAME]
    if not case_events:
        raise GoldenDatasetRegressionInputError(
            f"{role} run has no golden dataset evaluation events"
        )

    evaluations: dict[str, EvaluationResult] = {}
    for event in case_events:
        evaluation = _event_to_evaluation(event, role=role)
        case_id = evaluation.metadata.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise GoldenDatasetRegressionInputError(
                f"{role} evaluation event is missing metadata.case_id"
            )
        if case_id in evaluations:
            raise GoldenDatasetRegressionInputError(
                f"{role} run contains duplicate evaluation for case_id {case_id}"
            )
        evaluations[case_id] = evaluation
    return evaluations


def _event_to_evaluation(event: RunEvent, *, role: str) -> EvaluationResult:
    try:
        return EvaluationResult.model_validate(event.payload)
    except ValueError as exc:
        raise GoldenDatasetRegressionInputError(
            f"{role} evaluation event payload is invalid"
        ) from exc


def _ensure_matching_case_ids(
    baseline: dict[str, EvaluationResult],
    candidate: dict[str, EvaluationResult],
) -> None:
    baseline_ids = set(baseline)
    candidate_ids = set(candidate)
    if baseline_ids != candidate_ids:
        missing_candidate = sorted(baseline_ids - candidate_ids)
        missing_baseline = sorted(candidate_ids - baseline_ids)
        details = []
        if missing_candidate:
            details.append(f"missing candidate cases: {', '.join(missing_candidate)}")
        if missing_baseline:
            details.append(f"missing baseline cases: {', '.join(missing_baseline)}")
        raise GoldenDatasetRegressionInputError("; ".join(details))


def _compare_case(
    payload: GoldenDatasetRegressionCompareCreate,
    *,
    project_id: str,
    case_id: str,
    baseline: EvaluationResult,
    candidate: EvaluationResult,
    repository: TraceRepository,
) -> GoldenDatasetCaseRegressionReport:
    report = build_regression_report(
        RegressionComparisonCreate(
            baseline=EvaluationComparisonSubject(
                run_id=payload.baseline_run_id,
                version=payload.baseline_version,
                prompt_version=payload.baseline_prompt_version,
                model_version=payload.baseline_model_version,
                evaluation=_result_to_create(baseline),
            ),
            candidate=EvaluationComparisonSubject(
                run_id=payload.candidate_run_id,
                version=payload.candidate_version,
                prompt_version=payload.candidate_prompt_version,
                model_version=payload.candidate_model_version,
                evaluation=_result_to_create(candidate),
            ),
            regression_tolerance=payload.regression_tolerance,
            metadata={
                "agentops_kind": "golden_dataset_case_regression",
                "dataset_id": baseline.metadata.get("dataset_id"),
                "baseline_dataset_version": baseline.metadata.get("dataset_version"),
                "candidate_dataset_version": candidate.metadata.get("dataset_version"),
                "case_id": case_id,
                "request_metadata": payload.metadata,
            },
        ),
        project_id=project_id,
    )
    saved_report = repository.save_regression_report(report)
    return _case_report(case_id, saved_report)


def _result_to_create(result: EvaluationResult) -> EvaluationResultCreate:
    return EvaluationResultCreate(
        answer=result.answer,
        evaluator_name=result.evaluator_name,
        evaluator_id=result.evaluator_id,
        evaluator_version=result.evaluator_version,
        rubric_id=result.rubric_id,
        rubric_version=result.rubric_version,
        judge_model=result.judge_model,
        threshold_profile=result.threshold_profile,
        rag_event_id=result.rag_event_id,
        metrics=[
            EvaluationMetricInput(
                name=metric.name,
                score=metric.score,
                threshold=metric.threshold,
                direction=metric.direction,
                rationale=metric.rationale,
            )
            for metric in result.metrics
        ],
        metadata=result.metadata,
    )


def _case_report(
    case_id: str,
    report: RegressionReport,
) -> GoldenDatasetCaseRegressionReport:
    return GoldenDatasetCaseRegressionReport(
        case_id=case_id,
        report_id=report.id,
        status=report.status,
        baseline_verdict=report.baseline_verdict,
        candidate_verdict=report.candidate_verdict,
        metrics=report.metrics,
    )
