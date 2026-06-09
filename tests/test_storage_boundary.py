import pytest
from fastapi.testclient import TestClient

from agentops_api.main import create_app
from agentops_api.observability import (
    PostgresStorageUnavailableError,
    StorageBackend,
    TraceRepository,
    TraceRepositoryProtocol,
    create_trace_repository,
    load_storage_config,
)
from agentops_api.security import ApiKeyCredential, ApiScope

from tests.repository_contract import assert_trace_repository_contract


def test_sqlite_repository_satisfies_trace_repository_contract(tmp_path) -> None:
    counter = 0

    def make_repository() -> TraceRepository:
        nonlocal counter
        counter += 1
        return TraceRepository(tmp_path / f"contract-{counter}.db")

    repository = make_repository()

    assert isinstance(repository, TraceRepositoryProtocol)
    assert_trace_repository_contract(make_repository)


def test_storage_config_defaults_to_sqlite() -> None:
    config = load_storage_config()

    assert config.backend == StorageBackend.SQLITE
    assert config.sqlite_db_path.name == "agentops.db"
    assert config.database_url is None


def test_storage_config_supports_custom_sqlite_path(tmp_path) -> None:
    db_path = tmp_path / "custom-agentops.db"

    config = load_storage_config(backend="sqlite", sqlite_db_path=db_path)

    assert config.backend == StorageBackend.SQLITE
    assert config.sqlite_db_path == db_path


def test_storage_config_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="AGENTOPS_STORAGE_BACKEND"):
        load_storage_config(backend="mysql")


def test_postgres_storage_requires_database_url() -> None:
    with pytest.raises(ValueError, match="AGENTOPS_DATABASE_URL"):
        load_storage_config(backend="postgres")


def test_postgres_storage_boundary_fails_closed_without_adapter() -> None:
    secret_url = "postgresql://agentops:secret-password@localhost:5432/agentops"
    config = load_storage_config(backend="postgres", database_url=secret_url)

    with pytest.raises(PostgresStorageUnavailableError) as exc_info:
        create_trace_repository(config)

    assert "not implemented yet" in str(exc_info.value)
    assert "secret-password" not in str(exc_info.value)


def test_create_app_uses_sqlite_storage_config_from_environment(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "env-agentops.db"
    monkeypatch.setenv("AGENTOPS_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("AGENTOPS_DB_PATH", str(db_path))

    app = create_app(
        api_keys=[
            ApiKeyCredential(
                key="test-key",
                project_id="demo-project",
                scopes=[ApiScope.READ],
            )
        ]
    )

    assert app.state.storage_config.backend == StorageBackend.SQLITE
    assert app.state.storage_config.sqlite_db_path == db_path
    assert app.state.trace_repository.db_path == db_path


def test_create_app_accepts_injected_repository(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "injected.db")
    app = create_app(
        trace_repository=repository,
        api_keys=[
            ApiKeyCredential(
                key="test-key",
                project_id="demo-project",
                scopes=[ApiScope.READ],
            )
        ],
    )
    client = TestClient(app)

    response = client.get("/v1/runs", headers={"X-AgentOps-API-Key": "test-key"})

    assert response.status_code == 200
    assert app.state.trace_repository is repository
