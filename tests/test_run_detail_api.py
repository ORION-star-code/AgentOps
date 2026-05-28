def test_run_detail_contract_aggregates_timeline(make_client) -> None:
    client = make_client()
    run = client.post(
        "/v1/runs",
        json={"project_id": "demo-project", "name": "Debug RAG answer"},
    ).json()

    client.post(
        f"/v1/runs/{run['id']}/events",
        json={
            "type": "message",
            "name": "user_input",
            "payload": {"role": "user", "content": "Which policy applies?"},
        },
    )
    client.post(
        f"/v1/runs/{run['id']}/events",
        json={
            "type": "model_call",
            "name": "planner",
            "payload": {"token_count": 17, "latency_ms": 90},
        },
    )
    client.post(
        f"/v1/runs/{run['id']}/events",
        json={
            "type": "tool_call",
            "name": "retrieve_documents",
            "payload": {"token_count": 8, "latency_ms": 120},
        },
    )
    client.post(
        f"/v1/runs/{run['id']}/rag/evidence",
        json={
            "query": "Which policy applies?",
            "hit_status": "hit",
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "source_uri": "kb://policy/123",
                    "content_preview": "The policy applies to enterprise users.",
                }
            ],
            "citations": [{"chunk_id": "chunk-1"}],
        },
    )
    client.post(
        f"/v1/runs/{run['id']}/evaluations",
        json={
            "answer": "The policy applies to enterprise users.",
            "metrics": [
                {"name": "groundedness", "score": 0.9},
                {"name": "trustworthiness", "score": 0.85},
            ],
        },
    )
    client.post(
        f"/v1/runs/{run['id']}/events",
        json={
            "type": "error",
            "name": "retryable_tool_timeout",
            "payload": {"message": "first retrieval attempt timed out"},
        },
    )

    response = client.get(f"/v1/runs/{run['id']}/detail")

    assert response.status_code == 200
    detail = response.json()
    assert detail["run"]["id"] == run["id"]
    assert detail["summary"] == {
        "event_count": 6,
        "message_count": 1,
        "model_call_count": 1,
        "tool_call_count": 1,
        "rag_retrieval_count": 1,
        "evaluation_count": 1,
        "error_count": 1,
        "total_tokens": 25,
        "total_latency_ms": 210,
    }
    assert [event["sequence"] for event in detail["timeline"]] == [1, 2, 3, 4, 5, 6]
    assert detail["tool_calls"][0]["name"] == "retrieve_documents"
    assert detail["rag_evidence"][0]["payload"]["hit_status"] == "hit"
    assert detail["evaluations"][0]["payload"]["verdict"] == "pass"
    assert detail["errors"][0]["name"] == "retryable_tool_timeout"


def test_run_detail_returns_full_summary_with_recent_timeline_page(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()
    for index in range(105):
        client.post(
            f"/v1/runs/{run['id']}/events",
            json={
                "type": "custom",
                "name": f"event-{index}",
                "payload": {"token_count": 1, "latency_ms": 2},
            },
        )

    response = client.get(f"/v1/runs/{run['id']}/detail")

    assert response.status_code == 200
    detail = response.json()
    assert detail["summary"]["event_count"] == 105
    assert detail["summary"]["total_tokens"] == 105
    assert detail["summary"]["total_latency_ms"] == 210
    assert len(detail["timeline"]) == 100
    assert [event["sequence"] for event in detail["timeline"]] == list(range(6, 106))


def test_unknown_run_detail_returns_404(make_client) -> None:
    client = make_client()

    response = client.get("/v1/runs/missing-run/detail")

    assert response.status_code == 404
