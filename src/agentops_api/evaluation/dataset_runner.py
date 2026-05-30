"""Golden dataset execution service."""

from __future__ import annotations

from typing import Protocol

from agentops_api.evaluation.schemas import (
    EvaluationJudgeCreate,
    EvaluationMetricInput,
    EvaluationMetricName,
    EvaluationResultCreate,
    EvaluationVerdict,
    GoldenDatasetCase,
    GoldenDatasetCaseRunResult,
    GoldenDatasetCaseStatus,
    GoldenDatasetJudgeMode,
    GoldenDatasetRunCreate,
    GoldenDatasetRunResult,
    build_evaluation_result,
)
from agentops_api.observability import (
    AgentRunCreate,
    RunEventCreate,
    RunEventType,
    TraceRepository,
)

DETERMINISTIC_GOLDEN_EVALUATOR_ID = "agentops-deterministic-golden-runner"
DETERMINISTIC_GOLDEN_EVALUATOR_VERSION = "0.1.0"
CASE_EVALUATION_EVENT_NAME = "golden_dataset_case_evaluation"
SUMMARY_EVENT_NAME = "golden_dataset_summary"


class GoldenDatasetCaseInputError(ValueError):
    """Raised when a dataset case cannot produce an evaluation payload."""


class JudgeProvider(Protocol):
    """Minimal provider contract shared by Mimo and test doubles."""

    def evaluate(self, payload: EvaluationJudgeCreate) -> EvaluationResultCreate:
        """Generate an evaluation payload for one case."""


def run_golden_dataset(
    payload: GoldenDatasetRunCreate,
    *,
    repository: TraceRepository,
    judge_provider: JudgeProvider,
) -> GoldenDatasetRunResult:
    """Execute every case in a golden dataset and persist evaluation evidence."""

    run = repository.create_run(
        AgentRunCreate(
            project_id=payload.project_id,
            name=f"Golden dataset: {payload.dataset.dataset_id}@{payload.dataset.version}",
            metadata={
                "agentops_kind": "golden_dataset_run",
                "dataset_id": payload.dataset.dataset_id,
                "dataset_version": payload.dataset.version,
                "judge_mode": payload.judge_mode.value,
            },
        )
    )
    results = [
        _run_case(payload, case, run_id=run.id, repository=repository, judge_provider=judge_provider)
        for case in payload.dataset.cases
    ]
    passed_cases = sum(1 for result in results if result.status == GoldenDatasetCaseStatus.PASSED)
    failed_cases = len(results) - passed_cases
    summary_event = repository.append_event(
        run.id,
        RunEventCreate(
            type=RunEventType.CUSTOM,
            name=SUMMARY_EVENT_NAME,
            payload=_summary_payload(payload, results, passed_cases, failed_cases),
        ),
    )
    repository.complete_run(run.id)

    return GoldenDatasetRunResult(
        run_id=run.id,
        summary_event_id=summary_event.id,
        project_id=payload.project_id,
        dataset_id=payload.dataset.dataset_id,
        dataset_version=payload.dataset.version,
        judge_mode=payload.judge_mode,
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        results=results,
        metadata=payload.metadata,
    )


def _run_case(
    payload: GoldenDatasetRunCreate,
    case: GoldenDatasetCase,
    *,
    run_id: str,
    repository: TraceRepository,
    judge_provider: JudgeProvider,
) -> GoldenDatasetCaseRunResult:
    try:
        evaluation_payload = _build_case_evaluation_payload(payload, case, judge_provider)
        evaluation = build_evaluation_result(evaluation_payload)
        event = repository.append_event(
            run_id,
            RunEventCreate(
                type=RunEventType.EVALUATION,
                name=CASE_EVALUATION_EVENT_NAME,
                payload=evaluation.model_dump(mode="json"),
            ),
        )
    except Exception as exc:
        return GoldenDatasetCaseRunResult(
            case_id=case.case_id,
            status=GoldenDatasetCaseStatus.FAILED,
            error=_safe_error_message(exc),
        )

    case_status = (
        GoldenDatasetCaseStatus.PASSED
        if evaluation.verdict == EvaluationVerdict.PASS
        else GoldenDatasetCaseStatus.FAILED
    )
    return GoldenDatasetCaseRunResult(
        case_id=case.case_id,
        status=case_status,
        event_id=event.id,
        evaluation=evaluation,
    )


def _build_case_evaluation_payload(
    payload: GoldenDatasetRunCreate,
    case: GoldenDatasetCase,
    judge_provider: JudgeProvider,
) -> EvaluationResultCreate:
    if not case.expected_answer:
        raise GoldenDatasetCaseInputError(
            "golden dataset case requires expected_answer before evaluation"
        )

    metadata = _case_metadata(payload, case)
    if payload.judge_mode == GoldenDatasetJudgeMode.MIMO:
        return judge_provider.evaluate(
            EvaluationJudgeCreate(
                answer=case.expected_answer,
                question=case.user_input,
                context=case.reference_context,
                rubric_id=payload.rubric_id,
                rubric_version=payload.rubric_version,
                threshold_profile=payload.threshold_profile,
                metrics=payload.metrics,
                metadata=metadata,
            )
        )

    return EvaluationResultCreate(
        answer=case.expected_answer,
        evaluator_name=DETERMINISTIC_GOLDEN_EVALUATOR_ID,
        evaluator_id=DETERMINISTIC_GOLDEN_EVALUATOR_ID,
        evaluator_version=DETERMINISTIC_GOLDEN_EVALUATOR_VERSION,
        rubric_id=payload.rubric_id,
        rubric_version=payload.rubric_version,
        judge_model=None,
        threshold_profile=payload.threshold_profile,
        metrics=[_deterministic_metric(metric, case) for metric in payload.metrics],
        metadata=metadata,
    )


def _case_metadata(payload: GoldenDatasetRunCreate, case: GoldenDatasetCase) -> dict:
    return {
        "dataset_id": payload.dataset.dataset_id,
        "dataset_version": payload.dataset.version,
        "case_id": case.case_id,
        "risk_level": case.risk_level.value,
        "approval_required": case.approval_required,
        "expected_tools": case.expected_tools,
        "expected_tool_args": case.expected_tool_args,
        "case_metadata": case.metadata,
        "run_metadata": payload.metadata,
    }


def _deterministic_metric(
    metric: EvaluationMetricName,
    case: GoldenDatasetCase,
) -> EvaluationMetricInput:
    has_context = bool(case.reference_context)
    if metric == EvaluationMetricName.GROUNDEDNESS:
        return EvaluationMetricInput(
            name=metric,
            score=0.95 if has_context else 0.6,
            rationale=_rationale(
                positive="Expected answer is backed by reference context.",
                negative="No reference context was supplied for grounding.",
                passed=has_context,
            ),
        )
    if metric == EvaluationMetricName.CITATION_ACCURACY:
        return EvaluationMetricInput(
            name=metric,
            score=0.95 if has_context else 0.6,
            rationale=_rationale(
                positive="Reference context is available for citation checks.",
                negative="No reference context was supplied for citation checks.",
                passed=has_context,
            ),
        )
    if metric == EvaluationMetricName.HALLUCINATION_RISK:
        return EvaluationMetricInput(
            name=metric,
            score=0.05 if has_context else 0.35,
            rationale=_rationale(
                positive="Expected answer is constrained by reference context.",
                negative="Missing reference context raises hallucination risk.",
                passed=has_context,
            ),
        )
    return EvaluationMetricInput(
        name=metric,
        score=0.9 if has_context else 0.65,
        rationale=_rationale(
            positive="Expected answer has enough evidence for deterministic trust checks.",
            negative="Trustworthiness is limited without reference context.",
            passed=has_context,
        ),
    )


def _rationale(*, positive: str, negative: str, passed: bool) -> str:
    return positive if passed else negative


def _summary_payload(
    payload: GoldenDatasetRunCreate,
    results: list[GoldenDatasetCaseRunResult],
    passed_cases: int,
    failed_cases: int,
) -> dict:
    return {
        "dataset_id": payload.dataset.dataset_id,
        "dataset_version": payload.dataset.version,
        "judge_mode": payload.judge_mode.value,
        "total_cases": len(results),
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "case_results": [
            {
                "case_id": result.case_id,
                "status": result.status.value,
                "event_id": result.event_id,
                "verdict": result.evaluation.verdict.value if result.evaluation else None,
                "error": result.error,
            }
            for result in results
        ],
        "metadata": payload.metadata,
    }


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, GoldenDatasetCaseInputError):
        return str(exc)
    return f"{type(exc).__name__} during golden dataset case evaluation"
