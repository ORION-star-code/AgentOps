import pytest
from pydantic import ValidationError

from agentops_api.evaluation import (
    EvaluationMetricName,
    EvaluationResultCreate,
    EvaluationVerdict,
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
