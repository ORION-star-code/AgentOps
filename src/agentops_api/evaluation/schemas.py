"""Answer quality evaluation schemas."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentops_api.observability.schemas import JsonObject, validate_json_size


class EvaluationMetricName(StrEnum):
    """Supported answer quality metrics."""

    GROUNDEDNESS = "groundedness"
    CITATION_ACCURACY = "citation_accuracy"
    HALLUCINATION_RISK = "hallucination_risk"
    TRUSTWORTHINESS = "trustworthiness"


class EvaluationDirection(StrEnum):
    """How a metric score is compared with its threshold."""

    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN_OR_EQUAL = "lte"


class EvaluationVerdict(StrEnum):
    """Overall answer quality verdict."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class RegressionStatus(StrEnum):
    """Overall comparison status between two evaluation results."""

    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"


DEFAULT_METRIC_RULES: dict[EvaluationMetricName, tuple[EvaluationDirection, float]] = {
    EvaluationMetricName.GROUNDEDNESS: (EvaluationDirection.GREATER_THAN_OR_EQUAL, 0.7),
    EvaluationMetricName.CITATION_ACCURACY: (EvaluationDirection.GREATER_THAN_OR_EQUAL, 0.7),
    EvaluationMetricName.HALLUCINATION_RISK: (EvaluationDirection.LESS_THAN_OR_EQUAL, 0.3),
    EvaluationMetricName.TRUSTWORTHINESS: (EvaluationDirection.GREATER_THAN_OR_EQUAL, 0.7),
}


class EvaluationMetricInput(BaseModel):
    """Client-supplied score for one evaluation metric."""

    model_config = ConfigDict(extra="forbid")

    name: EvaluationMetricName
    score: float = Field(ge=0, le=1)
    threshold: float | None = Field(default=None, ge=0, le=1)
    direction: EvaluationDirection | None = None
    rationale: str | None = Field(default=None, max_length=4000)


class EvaluationMetric(BaseModel):
    """Normalized metric with server-computed pass/fail state."""

    name: EvaluationMetricName
    score: float
    threshold: float
    direction: EvaluationDirection
    passed: bool
    rationale: str | None = None


class EvaluationResultCreate(BaseModel):
    """Payload for recording an answer quality evaluation."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=16000)
    evaluator_name: str = Field(default="agentops-rule-evaluator", min_length=1, max_length=200)
    rag_event_id: str | None = Field(default=None, max_length=200)
    metrics: list[EvaluationMetricInput] = Field(min_length=1, max_length=20)
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_fit(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_json_size(value)

    @model_validator(mode="after")
    def metric_names_must_be_unique(self) -> EvaluationResultCreate:
        names = [metric.name for metric in self.metrics]
        if len(names) != len(set(names)):
            raise ValueError("evaluation metric names must be unique")
        return self


class EvaluationResult(BaseModel):
    """Structured answer quality evaluation result."""

    answer: str
    evaluator_name: str
    rag_event_id: str | None
    verdict: EvaluationVerdict
    metrics: list[EvaluationMetric]
    metadata: JsonObject


class EvaluationComparisonSubject(BaseModel):
    """One side of a regression comparison."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=200)
    prompt_version: str | None = Field(default=None, max_length=200)
    model_version: str | None = Field(default=None, max_length=200)
    evaluation: EvaluationResultCreate


class RegressionComparisonCreate(BaseModel):
    """Payload for comparing baseline and candidate evaluations."""

    model_config = ConfigDict(extra="forbid")

    baseline: EvaluationComparisonSubject
    candidate: EvaluationComparisonSubject
    regression_tolerance: float = Field(default=0.05, ge=0, le=1)
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_fit(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_json_size(value)

    @model_validator(mode="after")
    def compared_metrics_must_match(self) -> RegressionComparisonCreate:
        baseline_names = {metric.name for metric in self.baseline.evaluation.metrics}
        candidate_names = {metric.name for metric in self.candidate.evaluation.metrics}
        if baseline_names != candidate_names:
            raise ValueError("baseline and candidate evaluations must contain the same metric names")
        return self


class MetricRegressionComparison(BaseModel):
    """Metric-level quality delta between baseline and candidate."""

    name: EvaluationMetricName
    baseline_score: float
    candidate_score: float
    score_delta: float
    quality_delta: float
    direction: EvaluationDirection
    threshold: float
    regressed: bool
    improved: bool


class RegressionReport(BaseModel):
    """Computed regression report for a candidate Agent change."""

    baseline_run_id: str
    candidate_run_id: str
    baseline_version: str
    candidate_version: str
    baseline_prompt_version: str | None
    candidate_prompt_version: str | None
    baseline_model_version: str | None
    candidate_model_version: str | None
    baseline_verdict: EvaluationVerdict
    candidate_verdict: EvaluationVerdict
    status: RegressionStatus
    regression_tolerance: float
    metrics: list[MetricRegressionComparison]
    metadata: JsonObject


def build_evaluation_result(payload: EvaluationResultCreate) -> EvaluationResult:
    """Normalize metric rules and compute an aggregate verdict."""

    metrics = [_build_metric(metric) for metric in payload.metrics]
    passed_count = sum(1 for metric in metrics if metric.passed)
    if passed_count == len(metrics):
        verdict = EvaluationVerdict.PASS
    elif passed_count == 0:
        verdict = EvaluationVerdict.FAIL
    else:
        verdict = EvaluationVerdict.WARN

    return EvaluationResult(
        answer=payload.answer,
        evaluator_name=payload.evaluator_name,
        rag_event_id=payload.rag_event_id,
        verdict=verdict,
        metrics=metrics,
        metadata=payload.metadata,
    )


def build_regression_report(payload: RegressionComparisonCreate) -> RegressionReport:
    """Compare two evaluations and flag meaningful quality regressions."""

    baseline = build_evaluation_result(payload.baseline.evaluation)
    candidate = build_evaluation_result(payload.candidate.evaluation)
    baseline_by_name = {metric.name: metric for metric in baseline.metrics}
    candidate_by_name = {metric.name: metric for metric in candidate.metrics}

    metric_comparisons = [
        _compare_metric(
            baseline_by_name[name],
            candidate_by_name[name],
            payload.regression_tolerance,
        )
        for name in sorted(baseline_by_name)
    ]

    if any(metric.regressed for metric in metric_comparisons):
        status = RegressionStatus.REGRESSED
    elif any(metric.improved for metric in metric_comparisons):
        status = RegressionStatus.IMPROVED
    else:
        status = RegressionStatus.UNCHANGED

    return RegressionReport(
        baseline_run_id=payload.baseline.run_id,
        candidate_run_id=payload.candidate.run_id,
        baseline_version=payload.baseline.version,
        candidate_version=payload.candidate.version,
        baseline_prompt_version=payload.baseline.prompt_version,
        candidate_prompt_version=payload.candidate.prompt_version,
        baseline_model_version=payload.baseline.model_version,
        candidate_model_version=payload.candidate.model_version,
        baseline_verdict=baseline.verdict,
        candidate_verdict=candidate.verdict,
        status=status,
        regression_tolerance=payload.regression_tolerance,
        metrics=metric_comparisons,
        metadata=payload.metadata,
    )


def _build_metric(metric: EvaluationMetricInput) -> EvaluationMetric:
    default_direction, default_threshold = DEFAULT_METRIC_RULES[metric.name]
    direction = metric.direction or default_direction
    threshold = default_threshold if metric.threshold is None else metric.threshold
    if direction == EvaluationDirection.GREATER_THAN_OR_EQUAL:
        passed = metric.score >= threshold
    else:
        passed = metric.score <= threshold

    return EvaluationMetric(
        name=metric.name,
        score=metric.score,
        threshold=threshold,
        direction=direction,
        passed=passed,
        rationale=metric.rationale,
    )


def _compare_metric(
    baseline: EvaluationMetric,
    candidate: EvaluationMetric,
    regression_tolerance: float,
) -> MetricRegressionComparison:
    score_delta = candidate.score - baseline.score
    if baseline.direction == EvaluationDirection.GREATER_THAN_OR_EQUAL:
        quality_delta = score_delta
    else:
        quality_delta = -score_delta

    return MetricRegressionComparison(
        name=baseline.name,
        baseline_score=baseline.score,
        candidate_score=candidate.score,
        score_delta=score_delta,
        quality_delta=quality_delta,
        direction=baseline.direction,
        threshold=baseline.threshold,
        regressed=quality_delta < -regression_tolerance,
        improved=quality_delta > regression_tolerance,
    )
