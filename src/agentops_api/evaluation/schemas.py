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
