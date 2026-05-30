"""Answer quality evaluation schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentops_api.observability.schemas import JsonObject, now_utc, validate_json_size

DEFAULT_EVALUATOR_ID = "agentops-rule-evaluator"
DEFAULT_EVALUATOR_VERSION = "0.1.0"
DEFAULT_RUBRIC_ID = "agentops-answer-quality"
DEFAULT_RUBRIC_VERSION = "0.1.0"
DEFAULT_THRESHOLD_PROFILE = "default"


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


class GoldenDatasetRisk(StrEnum):
    """Risk tier for deterministic golden dataset cases."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GoldenDatasetJudgeMode(StrEnum):
    """Judge backend used for one golden dataset execution."""

    DETERMINISTIC = "deterministic"
    MIMO = "mimo"


class GoldenDatasetCaseStatus(StrEnum):
    """Execution status for one golden dataset case."""

    PASSED = "passed"
    FAILED = "failed"


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
    evaluator_name: str = Field(default=DEFAULT_EVALUATOR_ID, min_length=1, max_length=200)
    evaluator_id: str = Field(default=DEFAULT_EVALUATOR_ID, min_length=1, max_length=200)
    evaluator_version: str = Field(
        default=DEFAULT_EVALUATOR_VERSION,
        min_length=1,
        max_length=200,
    )
    rubric_id: str = Field(default=DEFAULT_RUBRIC_ID, min_length=1, max_length=200)
    rubric_version: str = Field(default=DEFAULT_RUBRIC_VERSION, min_length=1, max_length=200)
    judge_model: str | None = Field(default=None, max_length=200)
    threshold_profile: str = Field(
        default=DEFAULT_THRESHOLD_PROFILE,
        min_length=1,
        max_length=200,
    )
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


def _default_judge_metrics() -> list[EvaluationMetricName]:
    return [
        EvaluationMetricName.GROUNDEDNESS,
        EvaluationMetricName.CITATION_ACCURACY,
        EvaluationMetricName.HALLUCINATION_RISK,
        EvaluationMetricName.TRUSTWORTHINESS,
    ]


class EvaluationJudgeCreate(BaseModel):
    """Payload for generating an answer quality evaluation with an external judge."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=16000)
    question: str = Field(min_length=1, max_length=4000)
    context: list[Annotated[str, Field(max_length=16000)]] = Field(
        default_factory=list,
        max_length=50,
    )
    rag_event_id: str | None = Field(default=None, max_length=200)
    rubric_id: str = Field(default=DEFAULT_RUBRIC_ID, min_length=1, max_length=200)
    rubric_version: str = Field(default=DEFAULT_RUBRIC_VERSION, min_length=1, max_length=200)
    threshold_profile: str = Field(
        default=DEFAULT_THRESHOLD_PROFILE,
        min_length=1,
        max_length=200,
    )
    metrics: list[EvaluationMetricName] = Field(
        default_factory=_default_judge_metrics,
        min_length=1,
        max_length=4,
    )
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_fit(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_json_size(value)

    @model_validator(mode="after")
    def metric_names_must_be_unique(self) -> EvaluationJudgeCreate:
        if len(self.metrics) != len(set(self.metrics)):
            raise ValueError("judge metric names must be unique")
        return self


class EvaluationResult(BaseModel):
    """Structured answer quality evaluation result."""

    answer: str
    evaluator_name: str
    evaluator_id: str
    evaluator_version: str
    rubric_id: str
    rubric_version: str
    judge_model: str | None
    threshold_profile: str
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

    id: str
    project_id: str
    created_at: datetime
    baseline_run_id: str
    candidate_run_id: str
    baseline_version: str
    candidate_version: str
    baseline_prompt_version: str | None
    candidate_prompt_version: str | None
    baseline_model_version: str | None
    candidate_model_version: str | None
    baseline_evaluator_id: str
    candidate_evaluator_id: str
    baseline_evaluator_version: str
    candidate_evaluator_version: str
    baseline_rubric_id: str
    candidate_rubric_id: str
    baseline_rubric_version: str
    candidate_rubric_version: str
    baseline_judge_model: str | None
    candidate_judge_model: str | None
    baseline_threshold_profile: str
    candidate_threshold_profile: str
    baseline_verdict: EvaluationVerdict
    candidate_verdict: EvaluationVerdict
    status: RegressionStatus
    regression_tolerance: float
    metrics: list[MetricRegressionComparison]
    metadata: JsonObject


class GoldenDatasetCase(BaseModel):
    """One deterministic case for future automated Agent evaluation."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=200)
    user_input: str = Field(min_length=1, max_length=16000)
    reference_context: list[str] = Field(default_factory=list, max_length=50)
    expected_tools: list[str] = Field(default_factory=list, max_length=50)
    expected_tool_args: JsonObject = Field(default_factory=dict)
    expected_answer: str | None = Field(default=None, max_length=16000)
    risk_level: GoldenDatasetRisk = GoldenDatasetRisk.MEDIUM
    approval_required: bool = False
    judge_rubric: str = Field(min_length=1, max_length=4000)
    pass_criteria: str = Field(min_length=1, max_length=4000)
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("expected_tool_args", "metadata")
    @classmethod
    def json_objects_must_fit(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_json_size(value)


class GoldenDataset(BaseModel):
    """Versioned deterministic evaluation dataset contract."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=200)
    cases: list[GoldenDatasetCase] = Field(min_length=1, max_length=200)
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_fit(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_json_size(value)

    @model_validator(mode="after")
    def case_ids_must_be_unique(self) -> GoldenDataset:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("golden dataset case_id values must be unique")
        return self


class GoldenDatasetRunCreate(BaseModel):
    """Request for executing a versioned golden dataset."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=200)
    dataset: GoldenDataset
    judge_mode: GoldenDatasetJudgeMode = GoldenDatasetJudgeMode.DETERMINISTIC
    rubric_id: str = Field(default=DEFAULT_RUBRIC_ID, min_length=1, max_length=200)
    rubric_version: str = Field(default=DEFAULT_RUBRIC_VERSION, min_length=1, max_length=200)
    threshold_profile: str = Field(
        default=DEFAULT_THRESHOLD_PROFILE,
        min_length=1,
        max_length=200,
    )
    metrics: list[EvaluationMetricName] = Field(
        default_factory=_default_judge_metrics,
        min_length=1,
        max_length=4,
    )
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_fit(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_json_size(value)

    @model_validator(mode="after")
    def metric_names_must_be_unique(self) -> GoldenDatasetRunCreate:
        if len(self.metrics) != len(set(self.metrics)):
            raise ValueError("golden dataset metric names must be unique")
        return self


class GoldenDatasetCaseRunResult(BaseModel):
    """Result for one golden dataset case execution."""

    case_id: str
    status: GoldenDatasetCaseStatus
    event_id: str | None = None
    evaluation: EvaluationResult | None = None
    error: str | None = None


class GoldenDatasetRunResult(BaseModel):
    """Aggregate result for a golden dataset execution."""

    run_id: str
    summary_event_id: str | None = None
    project_id: str
    dataset_id: str
    dataset_version: str
    judge_mode: GoldenDatasetJudgeMode
    total_cases: int
    passed_cases: int
    failed_cases: int
    results: list[GoldenDatasetCaseRunResult]
    metadata: JsonObject


class GoldenDatasetRegressionCompareCreate(BaseModel):
    """Request for comparing two completed golden dataset runs."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=200)
    baseline_run_id: str = Field(min_length=1, max_length=200)
    candidate_run_id: str = Field(min_length=1, max_length=200)
    baseline_version: str = Field(min_length=1, max_length=200)
    candidate_version: str = Field(min_length=1, max_length=200)
    baseline_prompt_version: str | None = Field(default=None, max_length=200)
    candidate_prompt_version: str | None = Field(default=None, max_length=200)
    baseline_model_version: str | None = Field(default=None, max_length=200)
    candidate_model_version: str | None = Field(default=None, max_length=200)
    regression_tolerance: float = Field(default=0.05, ge=0, le=1)
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_fit(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_json_size(value)

    @model_validator(mode="after")
    def runs_must_be_distinct(self) -> GoldenDatasetRegressionCompareCreate:
        if self.baseline_run_id == self.candidate_run_id:
            raise ValueError("baseline_run_id and candidate_run_id must be different")
        return self


class GoldenDatasetCaseRegressionReport(BaseModel):
    """Regression report reference for one dataset case."""

    case_id: str
    report_id: str
    status: RegressionStatus
    baseline_verdict: EvaluationVerdict
    candidate_verdict: EvaluationVerdict
    metrics: list[MetricRegressionComparison]


class GoldenDatasetRegressionResult(BaseModel):
    """Aggregate comparison result for two golden dataset runs."""

    project_id: str
    baseline_run_id: str
    candidate_run_id: str
    dataset_id: str
    baseline_dataset_version: str
    candidate_dataset_version: str
    status: RegressionStatus
    regression_tolerance: float
    total_cases: int
    improved_cases: int
    unchanged_cases: int
    regressed_cases: int
    case_reports: list[GoldenDatasetCaseRegressionReport]
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
        evaluator_id=payload.evaluator_id,
        evaluator_version=payload.evaluator_version,
        rubric_id=payload.rubric_id,
        rubric_version=payload.rubric_version,
        judge_model=payload.judge_model,
        threshold_profile=payload.threshold_profile,
        rag_event_id=payload.rag_event_id,
        verdict=verdict,
        metrics=metrics,
        metadata=payload.metadata,
    )


def build_regression_report(
    payload: RegressionComparisonCreate,
    *,
    project_id: str = "unscoped",
    report_id: str | None = None,
    created_at: datetime | None = None,
) -> RegressionReport:
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
        id=report_id or str(uuid4()),
        project_id=project_id,
        created_at=created_at or now_utc(),
        baseline_run_id=payload.baseline.run_id,
        candidate_run_id=payload.candidate.run_id,
        baseline_version=payload.baseline.version,
        candidate_version=payload.candidate.version,
        baseline_prompt_version=payload.baseline.prompt_version,
        candidate_prompt_version=payload.candidate.prompt_version,
        baseline_model_version=payload.baseline.model_version,
        candidate_model_version=payload.candidate.model_version,
        baseline_evaluator_id=baseline.evaluator_id,
        candidate_evaluator_id=candidate.evaluator_id,
        baseline_evaluator_version=baseline.evaluator_version,
        candidate_evaluator_version=candidate.evaluator_version,
        baseline_rubric_id=baseline.rubric_id,
        candidate_rubric_id=candidate.rubric_id,
        baseline_rubric_version=baseline.rubric_version,
        candidate_rubric_version=candidate.rubric_version,
        baseline_judge_model=baseline.judge_model,
        candidate_judge_model=candidate.judge_model,
        baseline_threshold_profile=baseline.threshold_profile,
        candidate_threshold_profile=candidate.threshold_profile,
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
