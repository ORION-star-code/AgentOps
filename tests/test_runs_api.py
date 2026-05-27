from fastapi.testclient import TestClient

from agentops_api.main import create_app


def test_run_ingestion_and_timeline_query(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))

    create_run_response = client.post(
        "/v1/runs",
        json={
            "project_id": "demo-project",
            "session_id": "session-001",
            "name": "RAG answer debug run",
            "metadata": {"agent_framework": "langgraph"},
        },
    )

    assert create_run_response.status_code == 201
    run = create_run_response.json()
    assert run["id"]
    assert run["project_id"] == "demo-project"
    assert run["status"] == "running"
    assert run["started_at"]
    assert run["ended_at"] is None

    get_run_response = client.get(f"/v1/runs/{run['id']}")
    assert get_run_response.status_code == 200
    assert get_run_response.json()["id"] == run["id"]

    first_event_response = client.post(
        f"/v1/runs/{run['id']}/events",
        json={
            "type": "message",
            "name": "user_input",
            "payload": {"role": "user", "content": "Explain the retrieved policy."},
        },
    )
    second_event_response = client.post(
        f"/v1/runs/{run['id']}/events",
        json={
            "type": "tool_call",
            "name": "retrieve_documents",
            "payload": {"tool_name": "vector_search", "latency_ms": 128, "token_count": 42},
        },
    )

    assert first_event_response.status_code == 201
    assert second_event_response.status_code == 201
    assert first_event_response.json()["sequence"] == 1
    assert second_event_response.json()["sequence"] == 2

    events_response = client.get(f"/v1/runs/{run['id']}/events")
    assert events_response.status_code == 200
    assert [event["sequence"] for event in events_response.json()] == [1, 2]


def test_unknown_run_event_append_returns_404(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))

    response = client.post(
        "/v1/runs/missing-run/events",
        json={"type": "error", "payload": {"message": "not found"}},
    )

    assert response.status_code == 404


def test_invalid_event_type_returns_422(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/events",
        json={"type": "not_a_real_event", "payload": {}},
    )

    assert response.status_code == 422


def test_oversized_payload_returns_422(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/events",
        json={"type": "custom", "payload": {"text": "x" * (64 * 1024)}},
    )

    assert response.status_code == 422
