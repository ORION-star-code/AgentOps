import pytest
from pydantic import ValidationError

from agentops_api.evaluation import (
    RegressionComparisonCreate,
    RegressionStatus,
    build_regression_report,
)


def _subject(run_id: str, version: str, metrics: list[dict]) -> dict:
    return {
        "run_id": run_id,
        "version": version,
        "prompt_version": f"prompt-{version}",
        "model_version": "gpt-test",
        "evaluation": {
            "answer": "The policy applies to enterprise users.",
            "metrics": metrics,
        },
    }


def test_regression_report_flags_quality_drop() -> None:
    report = build_regression_report(
        RegressionComparisonCreate(
            baseline=_subject(
                "baseline-run",
                "v1",
                [
                    {"name": "groundedness", "score": 0.9},
                    {"name": "hallucination_risk", "score": 0.1},
                ],
            ),
            candidate=_subject(
                "candidate-run",
                "v2",
                [
                    {"name": "groundedness", "score": 0.75},
                    {"name": "hallucination_risk", "score": 0.2},
                ],
            ),
            regression_tolerance=0.05,
        )
    )

    assert report.status == RegressionStatus.REGRESSED
    assert report.baseline_version == "v1"
    assert report.candidate_version == "v2"
    assert [metric.regressed for metric in report.metrics] == [True, True]


def test_regression_report_flags_improvement() -> None:
    report = build_regression_report(
        RegressionComparisonCreate(
            baseline=_subject(
                "baseline-run",
                "v1",
                [
                    {"name": "groundedness", "score": 0.72},
                    {"name": "hallucination_risk", "score": 0.28},
                ],
            ),
            candidate=_subject(
                "candidate-run",
                "v2",
                [
                    {"name": "groundedness", "score": 0.9},
                    {"name": "hallucination_risk", "score": 0.1},
                ],
            ),
        )
    )

    assert report.status == RegressionStatus.IMPROVED
    assert all(metric.improved for metric in report.metrics)


def test_regression_report_flags_unchanged_within_tolerance() -> None:
    report = build_regression_report(
        RegressionComparisonCreate(
            baseline=_subject("baseline-run", "v1", [{"name": "trustworthiness", "score": 0.8}]),
            candidate=_subject("candidate-run", "v2", [{"name": "trustworthiness", "score": 0.77}]),
            regression_tolerance=0.05,
        )
    )

    assert report.status == RegressionStatus.UNCHANGED
    assert report.metrics[0].quality_delta == pytest.approx(-0.03)


def test_regression_comparison_requires_same_metric_names() -> None:
    with pytest.raises(ValidationError, match="same metric names"):
        RegressionComparisonCreate(
            baseline=_subject("baseline-run", "v1", [{"name": "groundedness", "score": 0.8}]),
            candidate=_subject("candidate-run", "v2", [{"name": "trustworthiness", "score": 0.8}]),
        )
