import json

from fastapi.testclient import TestClient

from agentops_api.main import create_app
from agentops_api.security import (
    ApiKeyCredential,
    ApiKeyStore,
    ApiScope,
    hash_api_key,
    load_api_key_credentials,
)


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


def test_plaintext_dev_key_is_stored_as_hash_only() -> None:
    credential = ApiKeyCredential(
        key="valid-key",
        key_id="local-dev",
        project_id="demo-project",
        scopes=[ApiScope.READ],
    )

    assert credential.key_hash == hash_api_key("valid-key")
    assert credential.key_id == "local-dev"
    assert not hasattr(credential, "key")


def test_hashed_api_key_config_authenticates_with_key_id() -> None:
    raw_config = json.dumps(
        [
            {
                "key_hash": hash_api_key("rotated-key"),
                "key_id": "key-2026-06",
                "project_id": "demo-project",
                "scopes": ["read", "ingest"],
            }
        ]
    )
    store = ApiKeyStore(load_api_key_credentials(raw_config))

    principal = store.authenticate("rotated-key")

    assert principal is not None
    assert principal.project_id == "demo-project"
    assert principal.key_id == "key-2026-06"
    assert principal.allows(ApiScope.READ)
    assert principal.allows(ApiScope.INGEST)
    assert not principal.allows(ApiScope.EVALUATE)


def test_revoked_api_key_is_rejected(tmp_path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "agentops.db",
            api_keys=[
                ApiKeyCredential(
                    key="old-key",
                    key_id="old",
                    project_id="demo-project",
                    scopes=[ApiScope.READ],
                    revoked=True,
                )
            ],
        )
    )

    response = client.get(
        "/v1/runs/missing-run",
        headers={"X-AgentOps-API-Key": "old-key"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


def test_api_key_rotation_accepts_new_key_and_rejects_revoked_old_key() -> None:
    store = ApiKeyStore(
        [
            ApiKeyCredential(
                key="old-key",
                key_id="old",
                project_id="demo-project",
                scopes=[ApiScope.READ],
                revoked=True,
            ),
            ApiKeyCredential(
                key_hash=hash_api_key("new-key"),
                key_id="new",
                project_id="demo-project",
                scopes=[ApiScope.READ, ApiScope.INGEST],
            ),
        ]
    )

    assert store.authenticate("old-key") is None
    principal = store.authenticate("new-key")
    assert principal is not None
    assert principal.key_id == "new"
    assert principal.allows(ApiScope.INGEST)


def test_api_key_config_rejects_ambiguous_key_material() -> None:
    raw_config = json.dumps(
        [
            {
                "key": "plain-key",
                "key_hash": hash_api_key("plain-key"),
                "project_id": "demo-project",
                "scopes": ["read"],
            }
        ]
    )

    try:
        load_api_key_credentials(raw_config)
    except ValueError as exc:
        assert str(exc) == "API key entry cannot include both key and key_hash"
    else:
        raise AssertionError("expected ambiguous API key config to fail")


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
