import json
from pathlib import Path

from fastapi.testclient import TestClient

from agentops_api.main import app


def test_feature_inventory_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "docs" / "features.json").read_text(encoding="utf-8"))

    assert len(data["features"]) >= 3


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "agentops-api",
    }
