from agentops_api.evaluation import (
    EvaluationResultCreate,
    GoldenDatasetCaseStatus,
    GoldenDatasetJudgeMode,
    GoldenDatasetRunCreate,
    run_golden_dataset,
)
from agentops_api.observability import RunEventType, RunStatus, TraceRepository


class FailingIfCalledJudgeProvider:
    calls = 0

    def evaluate(self, payload):
        self.calls += 1
        raise AssertionError("judge provider should not be called")


class FakeJudgeProvider:
    def __init__(self, result: EvaluationResultCreate) -> None:
        self.result = result
        self.calls = 0
        self.payloads = []

    def evaluate(self, payload):
        self.calls += 1
        self.payloads.append(payload)
        return self.result


def _repository(tmp_path) -> TraceRepository:
    return TraceRepository(tmp_path / "agentops.db")


def _case(case_id: str, *, expected_answer: str | None = "The policy applies to users.") -> dict:
    payload = {
        "case_id": case_id,
        "user_input": "Who does the policy apply to?",
        "reference_context": ["The policy applies to users."],
        "judge_rubric": "Answer must be grounded in the supplied context.",
        "pass_criteria": "All requested metrics must pass.",
    }
    if expected_answer is not None:
        payload["expected_answer"] = expected_answer
    return payload


def _run_payload(**overrides) -> GoldenDatasetRunCreate:
    payload = {
        "project_id": "demo-project",
        "dataset": {
            "dataset_id": "rag-trust-suite",
            "version": "2026.05.30",
            "cases": [_case("case-001")],
        },
        "rubric_id": "rag-answer-quality",
        "rubric_version": "v1",
        "threshold_profile": "strict",
        "metadata": {"suite": "nightly"},
    }
    payload.update(overrides)
    return GoldenDatasetRunCreate.model_validate(payload)


def test_deterministic_runner_creates_run_evaluation_and_summary(tmp_path) -> None:
    repository = _repository(tmp_path)
    provider = FailingIfCalledJudgeProvider()

    result = run_golden_dataset(
        _run_payload(),
        repository=repository,
        judge_provider=provider,
    )

    run = repository.get_run(result.run_id)
    assert provider.calls == 0
    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    assert run.name == "Golden dataset: rag-trust-suite@2026.05.30"
    assert result.total_cases == 1
    assert result.passed_cases == 1
    assert result.failed_cases == 0
    assert result.results[0].status == GoldenDatasetCaseStatus.PASSED
    assert result.results[0].event_id is not None
    assert result.results[0].evaluation is not None
    assert result.results[0].evaluation.rubric_id == "rag-answer-quality"
    assert result.results[0].evaluation.rubric_version == "v1"
    assert result.results[0].evaluation.threshold_profile == "strict"
    assert result.results[0].evaluation.metadata["case_id"] == "case-001"

    events = repository.list_events(result.run_id)
    assert [event.sequence for event in events] == [1, 2]
    assert [event.type for event in events] == [RunEventType.EVALUATION, RunEventType.CUSTOM]
    assert events[0].name == "golden_dataset_case_evaluation"
    assert events[1].name == "golden_dataset_summary"
    assert events[1].id == result.summary_event_id
    assert events[1].payload["passed_cases"] == 1


def test_deterministic_runner_keeps_successful_case_when_another_case_fails(tmp_path) -> None:
    repository = _repository(tmp_path)
    payload = _run_payload(
        dataset={
            "dataset_id": "rag-trust-suite",
            "version": "2026.05.30",
            "cases": [
                _case("case-001"),
                _case("case-002", expected_answer=None),
            ],
        }
    )

    result = run_golden_dataset(
        payload,
        repository=repository,
        judge_provider=FailingIfCalledJudgeProvider(),
    )

    assert result.total_cases == 2
    assert result.passed_cases == 1
    assert result.failed_cases == 1
    assert [case_result.case_id for case_result in result.results] == ["case-001", "case-002"]
    assert result.results[0].status == GoldenDatasetCaseStatus.PASSED
    assert result.results[0].event_id is not None
    assert result.results[1].status == GoldenDatasetCaseStatus.FAILED
    assert result.results[1].event_id is None
    assert result.results[1].evaluation is None
    assert result.results[1].error == "golden dataset case requires expected_answer before evaluation"

    events = repository.list_events(result.run_id)
    assert [event.name for event in events] == [
        "golden_dataset_case_evaluation",
        "golden_dataset_summary",
    ]
    assert events[-1].payload["failed_cases"] == 1
    assert events[-1].payload["case_results"][1]["status"] == "failed"


def test_mimo_mode_uses_injected_judge_provider(tmp_path) -> None:
    provider = FakeJudgeProvider(
        EvaluationResultCreate(
            answer="The policy applies to users.",
            evaluator_id="mimo-llm-judge",
            evaluator_version="0.1.0",
            rubric_id="rag-answer-quality",
            rubric_version="v1",
            judge_model="mimo-v2.5-pro",
            threshold_profile="strict",
            metrics=[
                {"name": "groundedness", "score": 0.9},
                {"name": "hallucination_risk", "score": 0.05},
            ],
            metadata={"provider": "fake"},
        )
    )

    result = run_golden_dataset(
        _run_payload(
            judge_mode=GoldenDatasetJudgeMode.MIMO,
            metrics=["groundedness", "hallucination_risk"],
        ),
        repository=_repository(tmp_path),
        judge_provider=provider,
    )

    assert provider.calls == 1
    assert provider.payloads[0].question == "Who does the policy apply to?"
    assert provider.payloads[0].metrics == ["groundedness", "hallucination_risk"]
    assert result.judge_mode == GoldenDatasetJudgeMode.MIMO
    assert result.results[0].evaluation is not None
    assert result.results[0].evaluation.judge_model == "mimo-v2.5-pro"
