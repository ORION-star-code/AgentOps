from agentops_api.evaluation import (
    EvaluationResultCreate,
    MimoJudgeAPIError,
    MimoJudgeNotConfiguredError,
    MimoJudgeResponseError,
    MimoJudgeTimeoutError,
)


class FakeMimoJudgeProvider:
    def __init__(self, result: EvaluationResultCreate | Exception) -> None:
        self.result = result
        self.calls = 0

    def evaluate(self, payload):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FailingIfCalledJudgeProvider:
    calls = 0

    def evaluate(self, payload):
        self.calls += 1
        raise AssertionError("judge provider should not be called")


def test_append_evaluation_to_run_timeline(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
            "evaluator_id": "groundedness-evaluator",
            "evaluator_version": "2026.05.29",
            "rubric_id": "enterprise-policy-rubric",
            "rubric_version": "v3",
            "judge_model": "deterministic-rule-engine",
            "threshold_profile": "strict",
            "rag_event_id": "rag-event-1",
            "metrics": [
                {"name": "groundedness", "score": 0.88},
                {"name": "citation_accuracy", "score": 0.9},
                {"name": "hallucination_risk", "score": 0.1},
                {"name": "trustworthiness", "score": 0.86},
            ],
        },
    )

    assert response.status_code == 201
    event = response.json()
    assert event["type"] == "evaluation"
    assert event["name"] == "answer_quality_evaluation"
    assert event["payload"]["verdict"] == "pass"
    assert event["payload"]["rag_event_id"] == "rag-event-1"
    assert event["payload"]["evaluator_id"] == "groundedness-evaluator"
    assert event["payload"]["evaluator_version"] == "2026.05.29"
    assert event["payload"]["rubric_id"] == "enterprise-policy-rubric"
    assert event["payload"]["rubric_version"] == "v3"
    assert event["payload"]["judge_model"] == "deterministic-rule-engine"
    assert event["payload"]["threshold_profile"] == "strict"
    assert [metric["passed"] for metric in event["payload"]["metrics"]] == [
        True,
        True,
        True,
        True,
    ]

    events_response = client.get(f"/v1/runs/{run['id']}/events")
    assert events_response.status_code == 200
    assert events_response.json()[0]["id"] == event["id"]


def test_evaluation_returns_warn_for_partial_metric_pass(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
            "metrics": [
                {"name": "groundedness", "score": 0.9},
                {"name": "trustworthiness", "score": 0.4},
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["payload"]["verdict"] == "warn"


def test_evaluation_rejects_duplicate_metrics(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
            "metrics": [
                {"name": "groundedness", "score": 0.8},
                {"name": "groundedness", "score": 0.9},
            ],
        },
    )

    assert response.status_code == 422


def test_evaluation_rejects_invalid_metric_score(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
            "metrics": [{"name": "hallucination_risk", "score": 1.2}],
        },
    )

    assert response.status_code == 422


def test_unknown_run_evaluation_returns_404(make_client) -> None:
    client = make_client()

    response = client.post(
        "/v1/runs/missing-run/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
            "metrics": [{"name": "groundedness", "score": 0.8}],
        },
    )

    assert response.status_code == 404


def test_finished_run_rejects_evaluation_append(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()
    client.post(f"/v1/runs/{run['id']}/complete")

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
            "metrics": [{"name": "groundedness", "score": 0.8}],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Run has already ended"


def test_mimo_judge_evaluation_to_run_timeline(make_client) -> None:
    provider = FakeMimoJudgeProvider(
        EvaluationResultCreate(
            answer="The policy applies to enterprise users.",
            evaluator_name="mimo-llm-judge",
            evaluator_id="mimo-llm-judge",
            evaluator_version="0.1.0",
            rubric_id="enterprise-policy",
            rubric_version="v1",
            judge_model="mimo-v2.5-pro",
            threshold_profile="strict",
            rag_event_id="rag-event-1",
            metrics=[
                {
                    "name": "groundedness",
                    "score": 0.86,
                    "rationale": "The answer is supported by supplied context.",
                },
                {
                    "name": "hallucination_risk",
                    "score": 0.12,
                    "rationale": "No unsupported claims were introduced.",
                },
            ],
            metadata={"dataset_id": "smoke"},
        )
    )
    client = make_client(mimo_judge_provider=provider)
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations/judge",
        json={
            "answer": "The policy applies to enterprise users.",
            "question": "Who does the policy apply to?",
            "context": ["The policy applies to enterprise users."],
            "rag_event_id": "rag-event-1",
            "rubric_id": "enterprise-policy",
            "rubric_version": "v1",
            "threshold_profile": "strict",
            "metrics": ["groundedness", "hallucination_risk"],
            "metadata": {"dataset_id": "smoke"},
        },
    )

    assert response.status_code == 201
    event = response.json()
    assert provider.calls == 1
    assert event["type"] == "evaluation"
    assert event["name"] == "mimo_judge_evaluation"
    assert event["payload"]["evaluator_id"] == "mimo-llm-judge"
    assert event["payload"]["evaluator_version"] == "0.1.0"
    assert event["payload"]["judge_model"] == "mimo-v2.5-pro"
    assert event["payload"]["rubric_id"] == "enterprise-policy"
    assert event["payload"]["rubric_version"] == "v1"
    assert event["payload"]["threshold_profile"] == "strict"
    assert event["payload"]["verdict"] == "pass"
    assert [metric["rationale"] for metric in event["payload"]["metrics"]] == [
        "The answer is supported by supplied context.",
        "No unsupported claims were introduced.",
    ]


def test_mimo_judge_returns_503_when_not_configured(make_client) -> None:
    client = make_client(
        mimo_judge_provider=FakeMimoJudgeProvider(
            MimoJudgeNotConfiguredError("missing key"),
        )
    )
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations/judge",
        json={
            "answer": "The policy applies to enterprise users.",
            "question": "Who does the policy apply to?",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Mimo judge API key is not configured"


def test_mimo_judge_maps_timeout_to_504(make_client) -> None:
    client = make_client(
        mimo_judge_provider=FakeMimoJudgeProvider(
            MimoJudgeTimeoutError("timeout"),
        )
    )
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations/judge",
        json={
            "answer": "The policy applies to enterprise users.",
            "question": "Who does the policy apply to?",
        },
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "Mimo judge request timed out"


def test_mimo_judge_maps_api_and_response_errors_to_502(make_client) -> None:
    for error in [
        MimoJudgeAPIError("api failed"),
        MimoJudgeResponseError("bad response"),
    ]:
        client = make_client(mimo_judge_provider=FakeMimoJudgeProvider(error))
        run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

        response = client.post(
            f"/v1/runs/{run['id']}/evaluations/judge",
            json={
                "answer": "The policy applies to enterprise users.",
                "question": "Who does the policy apply to?",
            },
        )

        assert response.status_code == 502
        assert response.json()["detail"] == "Mimo judge request failed"


def test_mimo_judge_unknown_run_returns_404_without_provider_call(make_client) -> None:
    provider = FailingIfCalledJudgeProvider()
    client = make_client(mimo_judge_provider=provider)

    response = client.post(
        "/v1/runs/missing-run/evaluations/judge",
        json={
            "answer": "The policy applies to enterprise users.",
            "question": "Who does the policy apply to?",
        },
    )

    assert response.status_code == 404
    assert provider.calls == 0


def test_mimo_judge_finished_run_returns_409_without_provider_call(make_client) -> None:
    provider = FailingIfCalledJudgeProvider()
    client = make_client(mimo_judge_provider=provider)
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()
    client.post(f"/v1/runs/{run['id']}/complete")

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations/judge",
        json={
            "answer": "The policy applies to enterprise users.",
            "question": "Who does the policy apply to?",
        },
    )

    assert response.status_code == 409
    assert provider.calls == 0


def test_mimo_judge_cross_project_returns_403_without_provider_call(make_client) -> None:
    provider = FailingIfCalledJudgeProvider()
    project_a_client = make_client(project_id="project-a", mimo_judge_provider=provider)
    run = project_a_client.post("/v1/runs", json={"project_id": "project-a"}).json()
    project_b_client = make_client(project_id="project-b", mimo_judge_provider=provider)

    response = project_b_client.post(
        f"/v1/runs/{run['id']}/evaluations/judge",
        json={
            "answer": "The policy applies to enterprise users.",
            "question": "Who does the policy apply to?",
        },
    )

    assert response.status_code == 403
    assert provider.calls == 0
