def test_append_rag_evidence_to_run_timeline(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
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
            "citations": [
                {
                    "chunk_id": "chunk-1",
                    "claim": "The policy applies to enterprise users.",
                    "quote": "applies to enterprise users",
                }
            ],
            "citation_coverage": 1,
        },
    )

    assert response.status_code == 201
    event = response.json()
    assert event["type"] == "rag_retrieval"
    assert event["name"] == "rag_evidence"
    assert event["payload"]["query"] == "What policy applies?"
    assert event["payload"]["hit_status"] == "hit"

    events_response = client.get(f"/v1/runs/{run['id']}/events")
    assert events_response.status_code == 200
    assert events_response.json()[0]["id"] == event["id"]


def test_rag_evidence_allows_empty_miss(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/rag/evidence",
        json={
            "query": "Unknown policy?",
            "hit_status": "miss",
            "chunks": [],
            "citations": [],
        },
    )

    assert response.status_code == 201
    assert response.json()["payload"]["hit_status"] == "miss"


def test_rag_evidence_rejects_unknown_citation_chunk(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/rag/evidence",
        json={
            "query": "What policy applies?",
            "hit_status": "hit",
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "source_uri": "kb://policy/123",
                    "content_preview": "The policy applies to enterprise users.",
                }
            ],
            "citations": [{"chunk_id": "missing-chunk"}],
        },
    )

    assert response.status_code == 422


def test_hit_rag_evidence_requires_citation(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/rag/evidence",
        json={
            "query": "What policy applies?",
            "hit_status": "hit",
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "source_uri": "kb://policy/123",
                    "content_preview": "The policy applies to enterprise users.",
                }
            ],
            "citations": [],
        },
    )

    assert response.status_code == 422


def test_unknown_run_rag_evidence_returns_404(make_client) -> None:
    client = make_client()

    response = client.post(
        "/v1/runs/missing-run/rag/evidence",
        json={
            "query": "Unknown policy?",
            "hit_status": "miss",
            "chunks": [],
            "citations": [],
        },
    )

    assert response.status_code == 404


def test_rag_evidence_redacts_nested_chunk_metadata(make_client) -> None:
    client = make_client()
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/rag/evidence",
        json={
            "query": "What policy applies?",
            "hit_status": "hit",
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "source_uri": "kb://policy/123",
                    "content_preview": "The policy applies to enterprise users.",
                    "metadata": {"cookie": "session=secret", "section": "policy"},
                }
            ],
            "citations": [{"chunk_id": "chunk-1"}],
        },
    )

    assert response.status_code == 201
    payload = response.json()["payload"]
    assert payload["chunks"][0]["metadata"]["cookie"] == "[REDACTED]"
    assert payload["chunks"][0]["metadata"]["section"] == "policy"
    assert payload["_agentops_redaction"]["redaction_count"] == 1
    assert "session=secret" not in str(payload)
