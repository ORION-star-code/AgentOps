from agentops_api.security import ApiScope


def test_run_ingestion_and_timeline_query(make_client) -> None:
    client = make_client()

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


def test_list_runs_returns_project_scoped_recent_runs(make_client) -> None:
    first_client = make_client()
    second_client = make_client(project_id="other-project")
    first_run = first_client.post(
        "/v1/runs",
        json={"project_id": "demo-project", "name": "project run"},
    ).json()
    second_run = second_client.post(
        "/v1/runs",
        json={"project_id": "other-project", "name": "other run"},
    ).json()

    response = first_client.get("/v1/runs")

    assert response.status_code == 200
    run_ids = [run["id"] for run in response.json()]
    assert first_run["id"] in run_ids
    assert second_run["id"] not in run_ids


def test_list_runs_supports_limit_and_status_filter(make_client) -> None:
    client = make_client()
    running_run = client.post(
        "/v1/runs",
        json={"project_id": "demo-project", "name": "running"},
    ).json()
    completed_run = client.post(
        "/v1/runs",
        json={"project_id": "demo-project", "name": "completed"},
    ).json()
    client.post(f"/v1/runs/{completed_run['id']}/complete")

    filtered_response = client.get("/v1/runs?status=succeeded&limit=1")
    invalid_limit_response = client.get("/v1/runs?limit=101")

    assert filtered_response.status_code == 200
    assert [run["id"] for run in filtered_response.json()] == [completed_run["id"]]
    assert running_run["id"] not in [run["id"] for run in filtered_response.json()]
    assert invalid_limit_response.status_code == 422


def test_list_runs_can_include_project_scoped_summary(make_client) -> None:
    client = make_client()
    other_client = make_client(project_id="other-project")
    run = client.post(
        "/v1/runs",
        json={"project_id": "demo-project", "name": "summary run"},
    ).json()
    other_run = other_client.post(
        "/v1/runs",
        json={"project_id": "other-project", "name": "other summary run"},
    ).json()
    client.post(
        f"/v1/runs/{run['id']}/events",
        json={
            "type": "message",
            "name": "user_input",
            "payload": {"content": "Debug this run."},
        },
    )
    client.post(
        f"/v1/runs/{run['id']}/events",
        json={
            "type": "model_call",
            "name": "planner",
            "payload": {"latency_ms": 320, "token_count": 90},
        },
    )
    client.post(
        f"/v1/runs/{run['id']}/events",
        json={
            "type": "tool_call",
            "name": "retrieve_documents",
            "payload": {"usage": {"latency_ms": 120, "token_count": 25}},
        },
    )
    client.post(
        f"/v1/runs/{run['id']}/rag/evidence",
        json={
            "query": "What policy applies?",
            "hit_status": "hit",
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "source_uri": "kb://policy/123",
                    "content_preview": "The policy applies to enterprise users.",
                    "score": 0.91,
                }
            ],
            "citations": [{"chunk_id": "chunk-1"}],
        },
    )
    client.post(
        f"/v1/runs/{run['id']}/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
            "metrics": [{"name": "groundedness", "score": 0.88}],
        },
    )
    client.post(
        f"/v1/runs/{run['id']}/events",
        json={"type": "error", "name": "retry", "payload": {"message": "Recovered."}},
    )
    other_client.post(
        f"/v1/runs/{other_run['id']}/events",
        json={"type": "error", "payload": {"message": "Other project."}},
    )

    plain_response = client.get("/v1/runs")
    summary_response = client.get("/v1/runs?include_summary=true")
    invalid_response = client.get("/v1/runs?include_summary=maybe")

    assert plain_response.status_code == 200
    assert "summary" not in plain_response.json()[0]
    assert summary_response.status_code == 200
    runs = {item["id"]: item for item in summary_response.json()}
    assert run["id"] in runs
    assert other_run["id"] not in runs
    summary = runs[run["id"]]["summary"]
    assert summary == {
        "event_count": 6,
        "message_count": 1,
        "model_call_count": 1,
        "tool_call_count": 1,
        "rag_retrieval_count": 1,
        "evaluation_count": 1,
        "error_count": 1,
        "total_tokens": 115,
        "total_latency_ms": 440,
    }
    assert invalid_response.status_code == 422


def test_list_runs_requires_read_scope(make_client) -> None:
    unauthenticated_client = make_client(include_auth_header=False)
    insufficient_client = make_client(scopes=[ApiScope.INGEST])

    unauthenticated_response = unauthenticated_client.get("/v1/runs")
    insufficient_scope_response = insufficient_client.get("/v1/runs")

    assert unauthenticated_response.status_code == 401
    assert insufficient_scope_response.status_code == 403


def test_timeline_query_supports_limit_cursor_and_type_filter(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()
    event_types = ["message", "tool_call", "message", "error", "custom"]
    for index, event_type in enumerate(event_types, start=1):
        client.post(
            f"/v1/runs/{run['id']}/events",
            json={
                "type": event_type,
                "name": f"event-{index}",
                "payload": {"index": index},
            },
        )

    first_page_response = client.get(f"/v1/runs/{run['id']}/events?limit=2")
    second_page_response = client.get(
        f"/v1/runs/{run['id']}/events?limit=2&after_sequence=2"
    )
    messages_response = client.get(f"/v1/runs/{run['id']}/events?type=message")

    assert first_page_response.status_code == 200
    assert [event["sequence"] for event in first_page_response.json()] == [1, 2]
    assert second_page_response.status_code == 200
    assert [event["sequence"] for event in second_page_response.json()] == [3, 4]
    assert messages_response.status_code == 200
    assert [event["sequence"] for event in messages_response.json()] == [1, 3]


def test_timeline_query_defaults_to_first_100_events(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()
    for index in range(105):
        client.post(
            f"/v1/runs/{run['id']}/events",
            json={
                "type": "custom",
                "name": f"event-{index}",
                "payload": {"index": index},
            },
        )

    default_response = client.get(f"/v1/runs/{run['id']}/events")
    tail_response = client.get(f"/v1/runs/{run['id']}/events?after_sequence=100")

    assert default_response.status_code == 200
    assert len(default_response.json()) == 100
    assert [event["sequence"] for event in default_response.json()] == list(range(1, 101))
    assert tail_response.status_code == 200
    assert [event["sequence"] for event in tail_response.json()] == [101, 102, 103, 104, 105]


def test_timeline_query_rejects_invalid_limit(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    zero_response = client.get(f"/v1/runs/{run['id']}/events?limit=0")
    too_large_response = client.get(f"/v1/runs/{run['id']}/events?limit=501")

    assert zero_response.status_code == 422
    assert too_large_response.status_code == 422


def test_unknown_run_event_append_returns_404(make_client) -> None:
    client = make_client()

    response = client.post(
        "/v1/runs/missing-run/events",
        json={"type": "error", "payload": {"message": "not found"}},
    )

    assert response.status_code == 404


def test_invalid_event_type_returns_422(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/events",
        json={"type": "not_a_real_event", "payload": {}},
    )

    assert response.status_code == 422


def test_generic_event_endpoint_rejects_typed_rag_and_evaluation_events(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    rag_response = client.post(
        f"/v1/runs/{run['id']}/events",
        json={"type": "rag_retrieval", "payload": {}},
    )
    evaluation_response = client.post(
        f"/v1/runs/{run['id']}/events",
        json={"type": "evaluation", "payload": {}},
    )

    assert rag_response.status_code == 422
    assert evaluation_response.status_code == 422
    assert rag_response.json()["detail"] == "Use the typed RAG or evaluation endpoint for this event type"
    assert evaluation_response.json()["detail"] == (
        "Use the typed RAG or evaluation endpoint for this event type"
    )


def test_oversized_payload_returns_422(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/events",
        json={"type": "custom", "payload": {"text": "x" * (64 * 1024)}},
    )

    assert response.status_code == 422


def test_run_api_returns_redacted_metadata(make_client) -> None:
    client = make_client()

    create_response = client.post(
        "/v1/runs",
        json={
            "project_id": "demo-project",
            "metadata": {"api_key": "sk-live-secret", "safe": "visible"},
        },
    )
    run = create_response.json()
    get_response = client.get(f"/v1/runs/{run['id']}")

    assert create_response.status_code == 201
    assert run["metadata"]["api_key"] == "[REDACTED]"
    assert run["metadata"]["safe"] == "visible"
    assert run["metadata"]["_agentops_redaction"]["redaction_count"] == 1
    assert get_response.json()["metadata"]["api_key"] == "[REDACTED]"
    assert "sk-live-secret" not in str(get_response.json())


def test_run_lifecycle_endpoints_set_terminal_status(make_client) -> None:
    client = make_client()
    complete_run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()
    failed_run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()
    canceled_run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    complete_response = client.post(f"/v1/runs/{complete_run['id']}/complete")
    fail_response = client.post(f"/v1/runs/{failed_run['id']}/fail")
    cancel_response = client.post(f"/v1/runs/{canceled_run['id']}/cancel")

    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "succeeded"
    assert complete_response.json()["ended_at"] is not None
    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "failed"
    assert fail_response.json()["ended_at"] is not None
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "canceled"
    assert cancel_response.json()["ended_at"] is not None


def test_finished_run_rejects_event_append_and_second_transition(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()
    complete_response = client.post(f"/v1/runs/{run['id']}/complete")

    event_response = client.post(
        f"/v1/runs/{run['id']}/events",
        json={"type": "message", "payload": {"role": "user"}},
    )
    second_transition_response = client.post(f"/v1/runs/{run['id']}/cancel")

    assert complete_response.status_code == 200
    assert event_response.status_code == 409
    assert event_response.json()["detail"] == "Run has already ended"
    assert second_transition_response.status_code == 409
    assert second_transition_response.json()["detail"] == "Run has already ended"


def test_unknown_run_lifecycle_returns_404(make_client) -> None:
    client = make_client()

    response = client.post("/v1/runs/missing-run/complete")

    assert response.status_code == 404
