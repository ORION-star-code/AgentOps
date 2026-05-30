import pytest

from agentops_api.evaluation import (
    EvaluationResultCreate,
    GoldenDatasetRegressionCompareCreate,
    GoldenDatasetRegressionInputError,
    GoldenDatasetRunNotCompleteError,
    RegressionStatus,
    build_evaluation_result,
    compare_golden_dataset_runs,
)
from agentops_api.evaluation.dataset_runner import CASE_EVALUATION_EVENT_NAME
from agentops_api.observability import (
    AgentRun,
    AgentRunCreate,
    RunEventCreate,
    RunEventType,
    TraceRepository,
)


def _repository(tmp_path) -> TraceRepository:
    return TraceRepository(tmp_path / "agentops.db")


def _comparison_payload(baseline_run_id: str, candidate_run_id: str) -> GoldenDatasetRegressionCompareCreate:
    return GoldenDatasetRegressionCompareCreate(
        project_id="demo-project",
        baseline_run_id=baseline_run_id,
        candidate_run_id=candidate_run_id,
        baseline_version="baseline-v1",
        candidate_version="candidate-v2",
        baseline_prompt_version="prompt-v1",
        candidate_prompt_version="prompt-v2",
        regression_tolerance=0.05,
        metadata={"suite": "nightly"},
    )


def _create_golden_run(
    repository: TraceRepository,
    *,
    dataset_id: str = "rag-trust-suite",
    dataset_version: str = "2026.05.30",
    case_scores: dict[str, float],
    complete: bool = True,
) -> AgentRun:
    run = repository.create_run(
        AgentRunCreate(
            project_id="demo-project",
            name=f"Golden dataset: {dataset_id}@{dataset_version}",
            metadata={
                "agentops_kind": "golden_dataset_run",
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "judge_mode": "deterministic",
            },
        )
    )
    for case_id, score in case_scores.items():
        evaluation = build_evaluation_result(
            EvaluationResultCreate(
                answer="The policy applies to enterprise users.",
                evaluator_id="agentops-deterministic-golden-runner",
                evaluator_version="0.1.0",
                rubric_id="rag-answer-quality",
                rubric_version="v1",
                threshold_profile="strict",
                metrics=[{"name": "groundedness", "score": score}],
                metadata={
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "case_id": case_id,
                },
            )
        )
        repository.append_event(
            run.id,
            RunEventCreate(
                type=RunEventType.EVALUATION,
                name=CASE_EVALUATION_EVENT_NAME,
                payload=evaluation.model_dump(mode="json"),
            ),
        )
    if complete:
        return repository.complete_run(run.id)
    return run


def test_compare_golden_dataset_runs_persists_case_reports(tmp_path) -> None:
    repository = _repository(tmp_path)
    baseline = _create_golden_run(
        repository,
        case_scores={"case-001": 0.9, "case-002": 0.72},
    )
    candidate = _create_golden_run(
        repository,
        case_scores={"case-001": 0.8, "case-002": 0.9},
    )

    result = compare_golden_dataset_runs(
        _comparison_payload(baseline.id, candidate.id),
        repository=repository,
        baseline_run=baseline,
        candidate_run=candidate,
        project_id="demo-project",
    )

    assert result.status == RegressionStatus.REGRESSED
    assert result.total_cases == 2
    assert result.regressed_cases == 1
    assert result.improved_cases == 1
    assert result.unchanged_cases == 0
    assert [case_report.case_id for case_report in result.case_reports] == [
        "case-001",
        "case-002",
    ]
    assert [case_report.status for case_report in result.case_reports] == [
        RegressionStatus.REGRESSED,
        RegressionStatus.IMPROVED,
    ]

    persisted = repository.get_regression_report(result.case_reports[0].report_id)
    assert persisted is not None
    assert persisted.metadata["case_id"] == "case-001"
    assert persisted.metadata["agentops_kind"] == "golden_dataset_case_regression"


def test_compare_golden_dataset_runs_requires_matching_case_ids(tmp_path) -> None:
    repository = _repository(tmp_path)
    baseline = _create_golden_run(repository, case_scores={"case-001": 0.9})
    candidate = _create_golden_run(repository, case_scores={"case-002": 0.9})

    with pytest.raises(GoldenDatasetRegressionInputError, match="missing candidate cases"):
        compare_golden_dataset_runs(
            _comparison_payload(baseline.id, candidate.id),
            repository=repository,
            baseline_run=baseline,
            candidate_run=candidate,
            project_id="demo-project",
        )


def test_compare_golden_dataset_runs_rejects_running_runs(tmp_path) -> None:
    repository = _repository(tmp_path)
    baseline = _create_golden_run(repository, case_scores={"case-001": 0.9}, complete=False)
    candidate = _create_golden_run(repository, case_scores={"case-001": 0.9})

    with pytest.raises(GoldenDatasetRunNotCompleteError, match="must be complete"):
        compare_golden_dataset_runs(
            _comparison_payload(baseline.id, candidate.id),
            repository=repository,
            baseline_run=baseline,
            candidate_run=candidate,
            project_id="demo-project",
        )


def test_compare_golden_dataset_runs_requires_same_dataset_id(tmp_path) -> None:
    repository = _repository(tmp_path)
    baseline = _create_golden_run(repository, dataset_id="rag-trust-suite", case_scores={"case-001": 0.9})
    candidate = _create_golden_run(repository, dataset_id="tool-trust-suite", case_scores={"case-001": 0.9})

    with pytest.raises(GoldenDatasetRegressionInputError, match="dataset_id values differ"):
        compare_golden_dataset_runs(
            _comparison_payload(baseline.id, candidate.id),
            repository=repository,
            baseline_run=baseline,
            candidate_run=candidate,
            project_id="demo-project",
        )
