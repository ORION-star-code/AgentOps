from fastapi.testclient import TestClient

from agentops_api.main import create_app


def test_append_evaluation_to_run_timeline(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
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
    assert [metric["passed"] for metric in event["payload"]["metrics"]] == [
        True,
        True,
        True,
        True,
    ]

    events_response = client.get(f"/v1/runs/{run['id']}/events")
    assert events_response.status_code == 200
    assert events_response.json()[0]["id"] == event["id"]


def test_evaluation_returns_warn_for_partial_metric_pass(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))
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


def test_evaluation_rejects_duplicate_metrics(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))
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


def test_evaluation_rejects_invalid_metric_score(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
            "metrics": [{"name": "hallucination_risk", "score": 1.2}],
        },
    )

    assert response.status_code == 422


def test_unknown_run_evaluation_returns_404(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))

    response = client.post(
        "/v1/runs/missing-run/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
            "metrics": [{"name": "groundedness", "score": 0.8}],
        },
    )

    assert response.status_code == 404
