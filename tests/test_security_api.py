from fastapi.testclient import TestClient

from agentops_api.main import create_app
from agentops_api.security import ApiKeyCredential, ApiScope


def _client_with_key(
    db_path,
    *,
    key: str,
    project_id: str,
    scopes: list[ApiScope],
) -> TestClient:
    client = TestClient(
        create_app(
            db_path,
            api_keys=[
                ApiKeyCredential(
                    key=key,
                    project_id=project_id,
                    scopes=scopes,
                )
            ],
        )
    )
    client.headers.update({"X-AgentOps-API-Key": key})
    return client


def test_v1_requires_api_key(tmp_path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "agentops.db",
            api_keys=[
                ApiKeyCredential(
                    key="valid-key",
                    project_id="demo-project",
                    scopes=[ApiScope.READ],
                )
            ],
        )
    )

    response = client.get("/v1/runs/missing-run")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API key"


def test_v1_rejects_invalid_api_key(tmp_path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "agentops.db",
            api_keys=[
                ApiKeyCredential(
                    key="valid-key",
                    project_id="demo-project",
                    scopes=[ApiScope.READ],
                )
            ],
        )
    )

    response = client.get(
        "/v1/runs/missing-run",
        headers={"X-AgentOps-API-Key": "wrong-key"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


def test_create_run_rejects_cross_project_payload(tmp_path) -> None:
    client = _client_with_key(
        tmp_path / "agentops.db",
        key="project-a-key",
        project_id="project-a",
        scopes=[ApiScope.INGEST],
    )

    response = client.post("/v1/runs", json={"project_id": "project-b"})

    assert response.status_code == 403
    assert response.json()["detail"] == "API key cannot access this project"


def test_run_read_rejects_cross_project_access(tmp_path) -> None:
    db_path = tmp_path / "agentops.db"
    project_a_client = _client_with_key(
        db_path,
        key="project-a-key",
        project_id="project-a",
        scopes=[ApiScope.INGEST, ApiScope.READ],
    )
    run = project_a_client.post("/v1/runs", json={"project_id": "project-a"}).json()

    project_b_client = _client_with_key(
        db_path,
        key="project-b-key",
        project_id="project-b",
        scopes=[ApiScope.READ],
    )
    response = project_b_client.get(f"/v1/runs/{run['id']}")

    assert response.status_code == 403
    assert response.json()["detail"] == "API key cannot access this project"


def test_scope_is_required_for_ingestion(tmp_path) -> None:
    client = _client_with_key(
        tmp_path / "agentops.db",
        key="read-only-key",
        project_id="demo-project",
        scopes=[ApiScope.READ],
    )

    response = client.post("/v1/runs", json={"project_id": "demo-project"})

    assert response.status_code == 403
    assert response.json()["detail"] == "API key does not have the required scope"


def test_evaluate_scope_is_required_for_regression_compare(tmp_path) -> None:
    client = _client_with_key(
        tmp_path / "agentops.db",
        key="ingest-only-key",
        project_id="demo-project",
        scopes=[ApiScope.INGEST],
    )

    response = client.post(
        "/v1/regressions/compare",
        json={
            "baseline": {
                "run_id": "baseline-run",
                "version": "v1",
                "evaluation": {
                    "answer": "Grounded answer.",
                    "metrics": [{"name": "groundedness", "score": 0.9}],
                },
            },
            "candidate": {
                "run_id": "candidate-run",
                "version": "v2",
                "evaluation": {
                    "answer": "Less grounded answer.",
                    "metrics": [{"name": "groundedness", "score": 0.8}],
                },
            },
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "API key does not have the required scope"


def test_evaluate_scope_is_required_for_regression_report_read(tmp_path) -> None:
    client = _client_with_key(
        tmp_path / "agentops.db",
        key="read-only-key",
        project_id="demo-project",
        scopes=[ApiScope.READ],
    )

    response = client.get("/v1/regressions/reports/missing-report")

    assert response.status_code == 403
    assert response.json()["detail"] == "API key does not have the required scope"


def test_evaluate_scope_is_required_for_mimo_judge(tmp_path) -> None:
    client = _client_with_key(
        tmp_path / "agentops.db",
        key="ingest-only-key",
        project_id="demo-project",
        scopes=[ApiScope.INGEST],
    )
    run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()

    response = client.post(
        f"/v1/runs/{run['id']}/evaluations/judge",
        json={
            "answer": "The policy applies to enterprise users.",
            "question": "Who does the policy apply to?",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "API key does not have the required scope"
