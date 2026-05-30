import pytest
from pydantic import ValidationError

from agentops_api.evaluation import (
    EvaluationJudgeCreate,
    EvaluationMetricName,
    EvaluationResultCreate,
    EvaluationVerdict,
    GoldenDataset,
    GoldenDatasetRegressionCompareCreate,
    GoldenDatasetJudgeMode,
    GoldenDatasetRunCreate,
    build_evaluation_result,
)


def test_evaluation_result_passes_when_all_metrics_pass() -> None:
    result = build_evaluation_result(
        EvaluationResultCreate(
            answer="The policy applies to enterprise users.",
            metrics=[
                {"name": "groundedness", "score": 0.88},
                {"name": "citation_accuracy", "score": 0.9},
                {"name": "hallucination_risk", "score": 0.1},
                {"name": "trustworthiness", "score": 0.86},
            ],
        )
    )

    assert result.verdict == EvaluationVerdict.PASS
    assert all(metric.passed for metric in result.metrics)
    hallucination_metric = next(
        metric for metric in result.metrics if metric.name == EvaluationMetricName.HALLUCINATION_RISK
    )
    assert hallucination_metric.direction == "lte"
    assert hallucination_metric.threshold == 0.3


def test_evaluation_result_records_reproducibility_metadata() -> None:
    result = build_evaluation_result(
        EvaluationResultCreate(
            answer="The policy applies to enterprise users.",
            evaluator_id="groundedness-evaluator",
            evaluator_version="2026.05.29",
            rubric_id="enterprise-policy-rubric",
            rubric_version="v3",
            judge_model="deterministic-rule-engine",
            threshold_profile="strict",
            metrics=[{"name": "groundedness", "score": 0.88}],
        )
    )

    assert result.evaluator_id == "groundedness-evaluator"
    assert result.evaluator_version == "2026.05.29"
    assert result.rubric_id == "enterprise-policy-rubric"
    assert result.rubric_version == "v3"
    assert result.judge_model == "deterministic-rule-engine"
    assert result.threshold_profile == "strict"


def test_evaluation_result_warns_when_some_metrics_fail() -> None:
    result = build_evaluation_result(
        EvaluationResultCreate(
            answer="The policy applies to enterprise users.",
            metrics=[
                {"name": "groundedness", "score": 0.9},
                {"name": "trustworthiness", "score": 0.4},
            ],
        )
    )

    assert result.verdict == EvaluationVerdict.WARN
    assert [metric.passed for metric in result.metrics] == [True, False]


def test_evaluation_result_fails_when_all_metrics_fail() -> None:
    result = build_evaluation_result(
        EvaluationResultCreate(
            answer="The policy applies to enterprise users.",
            metrics=[
                {"name": "groundedness", "score": 0.2},
                {"name": "hallucination_risk", "score": 0.9},
            ],
        )
    )

    assert result.verdict == EvaluationVerdict.FAIL


def test_duplicate_metric_names_are_rejected() -> None:
    with pytest.raises(ValidationError, match="metric names must be unique"):
        EvaluationResultCreate(
            answer="The policy applies to enterprise users.",
            metrics=[
                {"name": "groundedness", "score": 0.8},
                {"name": "groundedness", "score": 0.9},
            ],
        )


def test_metric_score_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        EvaluationResultCreate(
            answer="The policy applies to enterprise users.",
            metrics=[{"name": "trustworthiness", "score": 1.2}],
        )


def test_judge_payload_defaults_to_all_supported_metrics() -> None:
    payload = EvaluationJudgeCreate(
        answer="The policy applies to enterprise users.",
        question="Who does the policy apply to?",
    )

    assert payload.metrics == [
        EvaluationMetricName.GROUNDEDNESS,
        EvaluationMetricName.CITATION_ACCURACY,
        EvaluationMetricName.HALLUCINATION_RISK,
        EvaluationMetricName.TRUSTWORTHINESS,
    ]


def test_judge_payload_rejects_duplicate_metrics() -> None:
    with pytest.raises(ValidationError, match="judge metric names must be unique"):
        EvaluationJudgeCreate(
            answer="The policy applies to enterprise users.",
            question="Who does the policy apply to?",
            metrics=["groundedness", "groundedness"],
        )


def test_golden_dataset_accepts_versioned_cases() -> None:
    dataset = GoldenDataset(
        dataset_id="rag-trust-suite",
        version="2026.05.29",
        cases=[
            {
                "case_id": "policy-answer-001",
                "user_input": "Who does the policy apply to?",
                "reference_context": ["The policy applies to enterprise users."],
                "expected_tools": ["retrieve_documents"],
                "expected_tool_args": {"query": "policy applies to"},
                "expected_answer": "The policy applies to enterprise users.",
                "risk_level": "medium",
                "approval_required": False,
                "judge_rubric": "Answer must be grounded in retrieved policy text.",
                "pass_criteria": "Groundedness score must pass the configured threshold.",
            }
        ],
    )

    assert dataset.dataset_id == "rag-trust-suite"
    assert dataset.cases[0].case_id == "policy-answer-001"


def test_golden_dataset_rejects_duplicate_case_ids() -> None:
    case = {
        "case_id": "duplicate",
        "user_input": "Who does the policy apply to?",
        "judge_rubric": "Answer must be grounded.",
        "pass_criteria": "Groundedness score must pass.",
    }

    with pytest.raises(ValidationError, match="case_id values must be unique"):
        GoldenDataset(
            dataset_id="rag-trust-suite",
            version="2026.05.29",
            cases=[case, case],
        )


def test_golden_dataset_run_request_defaults_to_deterministic_judge() -> None:
    request = GoldenDatasetRunCreate(
        project_id="demo-project",
        dataset={
            "dataset_id": "rag-trust-suite",
            "version": "2026.05.30",
            "cases": [
                {
                    "case_id": "policy-answer-001",
                    "user_input": "Who does the policy apply to?",
                    "reference_context": ["The policy applies to enterprise users."],
                    "expected_answer": "The policy applies to enterprise users.",
                    "judge_rubric": "Answer must be grounded.",
                    "pass_criteria": "All metrics pass.",
                }
            ],
        },
    )

    assert request.judge_mode == GoldenDatasetJudgeMode.DETERMINISTIC
    assert request.metrics == [
        EvaluationMetricName.GROUNDEDNESS,
        EvaluationMetricName.CITATION_ACCURACY,
        EvaluationMetricName.HALLUCINATION_RISK,
        EvaluationMetricName.TRUSTWORTHINESS,
    ]


def test_golden_dataset_run_request_rejects_duplicate_metrics() -> None:
    with pytest.raises(ValidationError, match="metric names must be unique"):
        GoldenDatasetRunCreate(
            project_id="demo-project",
            dataset={
                "dataset_id": "rag-trust-suite",
                "version": "2026.05.30",
                "cases": [
                    {
                        "case_id": "policy-answer-001",
                        "user_input": "Who does the policy apply to?",
                        "expected_answer": "The policy applies to enterprise users.",
                        "judge_rubric": "Answer must be grounded.",
                        "pass_criteria": "All metrics pass.",
                    }
                ],
            },
            metrics=["groundedness", "groundedness"],
        )


def test_golden_dataset_regression_request_rejects_same_run_ids() -> None:
    with pytest.raises(ValidationError, match="must be different"):
        GoldenDatasetRegressionCompareCreate(
            project_id="demo-project",
            baseline_run_id="same-run",
            candidate_run_id="same-run",
            baseline_version="baseline-v1",
            candidate_version="candidate-v2",
        )
