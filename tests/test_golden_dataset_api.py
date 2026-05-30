from agentops_api.evaluation import EvaluationResultCreate
from agentops_api.security import ApiScope


class FakeJudgeProvider:
    def __init__(self, result: EvaluationResultCreate) -> None:
        self.result = result
        self.calls = 0

    def evaluate(self, payload):
        self.calls += 1
        return self.result


class FailingIfCalledJudgeProvider:
    calls = 0

    def evaluate(self, payload):
        self.calls += 1
        raise AssertionError("judge provider should not be called")


def _dataset_run_payload(**overrides) -> dict:
    payload = {
        "project_id": "demo-project",
        "dataset": {
            "dataset_id": "rag-trust-suite",
            "version": "2026.05.30",
            "cases": [
                {
                    "case_id": "case-001",
                    "user_input": "Who does the policy apply to?",
                    "reference_context": ["The policy applies to enterprise users."],
                    "expected_answer": "The policy applies to enterprise users.",
                    "expected_tools": ["retrieve_documents"],
                    "expected_tool_args": {"query": "policy applies to"},
                    "judge_rubric": "Answer must be grounded in retrieved policy text.",
                    "pass_criteria": "All requested metrics must pass.",
                }
            ],
        },
        "rubric_id": "rag-answer-quality",
        "rubric_version": "v1",
        "threshold_profile": "strict",
        "metadata": {"suite": "nightly"},
    }
    payload.update(overrides)
    return payload


def test_golden_dataset_run_requires_api_key(make_client) -> None:
    client = make_client(include_auth_header=False)

    response = client.post("/v1/golden-datasets/runs", json=_dataset_run_payload())

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API key"


def test_golden_dataset_run_requires_evaluate_scope(make_client) -> None:
    client = make_client(scopes=[ApiScope.READ])

    response = client.post("/v1/golden-datasets/runs", json=_dataset_run_payload())

    assert response.status_code == 403
    assert response.json()["detail"] == "API key does not have the required scope"


def test_golden_dataset_run_rejects_cross_project_payload(make_client) -> None:
    provider = FailingIfCalledJudgeProvider()
    client = make_client(project_id="project-a", mimo_judge_provider=provider)

    response = client.post(
        "/v1/golden-datasets/runs",
        json=_dataset_run_payload(project_id="project-b"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "API key cannot access this project"
    assert provider.calls == 0


def test_deterministic_golden_dataset_run_creates_queryable_evaluation_events(make_client) -> None:
    provider = FailingIfCalledJudgeProvider()
    client = make_client(mimo_judge_provider=provider)

    response = client.post("/v1/golden-datasets/runs", json=_dataset_run_payload())

    assert response.status_code == 201
    result = response.json()
    assert provider.calls == 0
    assert result["project_id"] == "demo-project"
    assert result["dataset_id"] == "rag-trust-suite"
    assert result["dataset_version"] == "2026.05.30"
    assert result["judge_mode"] == "deterministic"
    assert result["total_cases"] == 1
    assert result["passed_cases"] == 1
    assert result["failed_cases"] == 0
    assert result["results"][0]["case_id"] == "case-001"
    assert result["results"][0]["status"] == "passed"
    assert result["results"][0]["evaluation"]["metadata"]["case_id"] == "case-001"
    assert result["results"][0]["evaluation"]["rubric_id"] == "rag-answer-quality"

    detail_response = client.get(f"/v1/runs/{result['run_id']}/detail")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["run"]["status"] == "succeeded"
    assert detail["summary"]["event_count"] == 2
    assert detail["summary"]["evaluation_count"] == 1
    assert detail["timeline"][0]["name"] == "golden_dataset_case_evaluation"
    assert detail["timeline"][1]["name"] == "golden_dataset_summary"
    assert detail["evaluations"][0]["payload"]["metadata"]["case_id"] == "case-001"


def test_golden_dataset_run_returns_partial_case_failures(make_client) -> None:
    client = make_client(mimo_judge_provider=FailingIfCalledJudgeProvider())
    response = client.post(
        "/v1/golden-datasets/runs",
        json=_dataset_run_payload(
            dataset={
                "dataset_id": "rag-trust-suite",
                "version": "2026.05.30",
                "cases": [
                    _dataset_run_payload()["dataset"]["cases"][0],
                    {
                        "case_id": "case-002",
                        "user_input": "Who owns approval?",
                        "reference_context": ["High risk actions require approval."],
                        "judge_rubric": "Answer must identify approval requirement.",
                        "pass_criteria": "The case must include an expected answer.",
                    },
                ],
            }
        ),
    )

    assert response.status_code == 201
    result = response.json()
    assert result["total_cases"] == 2
    assert result["passed_cases"] == 1
    assert result["failed_cases"] == 1
    assert result["results"][1]["status"] == "failed"
    assert result["results"][1]["event_id"] is None
    assert result["results"][1]["evaluation"] is None
    assert result["results"][1]["error"] == (
        "golden dataset case requires expected_answer before evaluation"
    )


def test_golden_dataset_run_rejects_invalid_judge_mode(make_client) -> None:
    client = make_client()
    payload = _dataset_run_payload(judge_mode="unsupported")

    response = client.post("/v1/golden-datasets/runs", json=payload)

    assert response.status_code == 422


def test_golden_dataset_run_rejects_empty_dataset(make_client) -> None:
    client = make_client()
    payload = _dataset_run_payload(dataset={"dataset_id": "empty", "version": "v1", "cases": []})

    response = client.post("/v1/golden-datasets/runs", json=payload)

    assert response.status_code == 422


def test_mimo_golden_dataset_mode_uses_injected_provider(make_client) -> None:
    provider = FakeJudgeProvider(
        EvaluationResultCreate(
            answer="The policy applies to enterprise users.",
            evaluator_id="mimo-llm-judge",
            evaluator_version="0.1.0",
            rubric_id="rag-answer-quality",
            rubric_version="v1",
            judge_model="mimo-v2.5-pro",
            threshold_profile="strict",
            metrics=[
                {"name": "groundedness", "score": 0.91},
                {"name": "hallucination_risk", "score": 0.05},
            ],
            metadata={"provider": "fake"},
        )
    )
    client = make_client(mimo_judge_provider=provider)

    response = client.post(
        "/v1/golden-datasets/runs",
        json=_dataset_run_payload(
            judge_mode="mimo",
            metrics=["groundedness", "hallucination_risk"],
        ),
    )

    assert response.status_code == 201
    result = response.json()
    assert provider.calls == 1
    assert result["judge_mode"] == "mimo"
    assert result["passed_cases"] == 1
    assert result["results"][0]["evaluation"]["judge_model"] == "mimo-v2.5-pro"
