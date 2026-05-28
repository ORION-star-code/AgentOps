import pytest
from fastapi.testclient import TestClient

from agentops_api.main import create_app
from agentops_api.security import ApiKeyCredential, ApiScope

TEST_API_KEY = "test-agentops-key"
TEST_PROJECT_ID = "demo-project"


@pytest.fixture
def make_client(tmp_path):
    def factory(
        *,
        project_id: str = TEST_PROJECT_ID,
        scopes: list[ApiScope] | None = None,
        include_auth_header: bool = True,
    ) -> TestClient:
        credential = ApiKeyCredential(
            key=TEST_API_KEY,
            project_id=project_id,
            scopes=scopes or [ApiScope.INGEST, ApiScope.READ, ApiScope.EVALUATE],
        )
        client = TestClient(create_app(tmp_path / "agentops.db", api_keys=[credential]))
        if include_auth_header:
            client.headers.update({"X-AgentOps-API-Key": TEST_API_KEY})
        return client

    return factory
