from fastapi.testclient import TestClient

from agentops_api.audit import AuditOutcome
from agentops_api.main import create_app
from agentops_api.security import ApiKeyCredential, ApiScope


def _client_with_key(
    db_path,
    *,
    key: str,
    project_id: str = "demo-project",
    scopes: list[ApiScope] | None = None,
    key_id: str | None = "test-key",
    include_auth_header: bool = True,
) -> TestClient:
    client = TestClient(
        create_app(
            db_path,
            api_keys=[
                ApiKeyCredential(
                    key=key,
                    key_id=key_id,
                    project_id=project_id,
                    scopes=scopes or [ApiScope.INGEST, ApiScope.READ, ApiScope.EVALUATE],
                )
            ],
        )
    )
    if include_auth_header:
        client.headers.update({"X-AgentOps-API-Key": key})
    return client


def test_successful_v1_request_writes_non_sensitive_audit_event(tmp_path) -> None:
    raw_key = "super-secret-audit-key"
    client = _client_with_key(
        tmp_path / "agentops.db",
        key=raw_key,
        key_id="ingest-key-2026-06",
        scopes=[ApiScope.INGEST],
    )

    response = client.post("/v1/runs", json={"project_id": "demo-project"})

    assert response.status_code == 201
    events = client.app.state.trace_repository.list_audit_events(project_id="demo-project")
    assert len(events) == 1
    event = events[0]
    assert event.project_id == "demo-project"
    assert event.key_id == "ingest-key-2026-06"
    assert event.scope == ApiScope.INGEST.value
    assert event.method == "POST"
    assert event.path == "/v1/runs"
    assert event.status_code == 201
    assert event.outcome == AuditOutcome.SUCCEEDED
    assert event.reason == "request_completed"
    assert raw_key not in str(event.model_dump())
    assert not hasattr(event, "payload")


def test_missing_api_key_request_is_audited_without_project_context(tmp_path) -> None:
    client = _client_with_key(
        tmp_path / "agentops.db",
        key="valid-key",
        scopes=[ApiScope.READ],
        include_auth_header=False,
    )

    response = client.get("/v1/runs/missing-run")

    assert response.status_code == 401
    event = client.app.state.trace_repository.list_audit_events(limit=1)[0]
    assert event.project_id is None
    assert event.key_id is None
    assert event.scope == ApiScope.READ.value
    assert event.path == "/v1/runs/missing-run"
    assert event.status_code == 401
    assert event.outcome == AuditOutcome.FAILED
    assert event.reason == "missing_api_key"


def test_invalid_api_key_request_is_audited_without_storing_key(tmp_path) -> None:
    invalid_key = "wrong-secret-key"
    client = _client_with_key(
        tmp_path / "agentops.db",
        key="valid-key",
        scopes=[ApiScope.READ],
        include_auth_header=False,
    )

    response = client.get(
        "/v1/runs/missing-run",
        headers={"X-AgentOps-API-Key": invalid_key},
    )

    assert response.status_code == 401
    event = client.app.state.trace_repository.list_audit_events(limit=1)[0]
    assert event.project_id is None
    assert event.key_id is None
    assert event.scope == ApiScope.READ.value
    assert event.status_code == 401
    assert event.reason == "invalid_api_key"
    assert invalid_key not in str(event.model_dump())


def test_insufficient_scope_request_records_project_and_key_id(tmp_path) -> None:
    client = _client_with_key(
        tmp_path / "agentops.db",
        key="read-only-key",
        key_id="read-key-2026-06",
        scopes=[ApiScope.READ],
    )

    response = client.post("/v1/runs", json={"project_id": "demo-project"})

    assert response.status_code == 403
    event = client.app.state.trace_repository.list_audit_events(project_id="demo-project")[0]
    assert event.project_id == "demo-project"
    assert event.key_id == "read-key-2026-06"
    assert event.scope == ApiScope.INGEST.value
    assert event.status_code == 403
    assert event.outcome == AuditOutcome.FAILED
    assert event.reason == "insufficient_scope"


def test_route_level_project_rejection_is_audited_without_query_or_payload(tmp_path) -> None:
    client = _client_with_key(
        tmp_path / "agentops.db",
        key="project-a-key",
        key_id="project-a-key-id",
        project_id="project-a",
        scopes=[ApiScope.INGEST, ApiScope.READ],
    )

    response = client.post(
        "/v1/runs?debug=true",
        json={"project_id": "project-b", "metadata": {"token": "secret"}},
    )

    assert response.status_code == 403
    event = client.app.state.trace_repository.list_audit_events(project_id="project-a")[0]
    assert event.project_id == "project-a"
    assert event.key_id == "project-a-key-id"
    assert event.scope == ApiScope.INGEST.value
    assert event.path == "/v1/runs"
    assert "?" not in event.path
    assert event.status_code == 403
    assert event.reason == "request_failed"
    audit_dump = str(event.model_dump())
    assert "project-b" not in audit_dump
    assert "secret" not in audit_dump


def test_public_health_route_is_not_audited(tmp_path) -> None:
    client = _client_with_key(
        tmp_path / "agentops.db",
        key="valid-key",
        scopes=[ApiScope.READ],
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert client.app.state.trace_repository.list_audit_events() == []
