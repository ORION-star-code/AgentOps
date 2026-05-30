$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not $env:AGENTOPS_MIMO_API_KEY) {
    Write-Output "Mimo smoke skipped: set AGENTOPS_MIMO_API_KEY to run the live smoke test."
    exit 0
}

$SmokeCode = @'
import json
import tempfile

from fastapi.testclient import TestClient

from agentops_api.main import create_app
from agentops_api.security import ApiKeyCredential, ApiScope

with tempfile.TemporaryDirectory() as tmpdir:
    app = create_app(
        f"{tmpdir}/agentops-smoke.db",
        api_keys=[
            ApiKeyCredential(
                key="local-smoke-agentops-key",
                project_id="demo-project",
                scopes=[ApiScope.INGEST, ApiScope.READ, ApiScope.EVALUATE],
            )
        ],
    )
    client = TestClient(app)
    client.headers.update({"X-AgentOps-API-Key": "local-smoke-agentops-key"})

    run_response = client.post(
        "/v1/runs",
        json={
            "project_id": "demo-project",
            "name": "Mimo judge smoke run",
            "metadata": {"smoke": "mimo"},
        },
    )
    run_response.raise_for_status()
    run = run_response.json()

    judge_response = client.post(
        f"/v1/runs/{run['id']}/evaluations/judge",
        json={
            "question": "Who does the policy apply to?",
            "answer": "The policy applies to enterprise users.",
            "context": ["The policy applies to enterprise users."],
            "metrics": ["groundedness", "hallucination_risk"],
            "rubric_id": "mimo-smoke-rubric",
            "rubric_version": "v1",
            "threshold_profile": "default",
            "metadata": {"smoke": "mimo"},
        },
    )
    judge_response.raise_for_status()
    event = judge_response.json()

    detail_response = client.get(f"/v1/runs/{run['id']}/detail")
    detail_response.raise_for_status()

    print(
        json.dumps(
            {
                "status": "passed",
                "run_id": run["id"],
                "event_id": event["id"],
                "judge_model": event["payload"]["judge_model"],
                "verdict": event["payload"]["verdict"],
            },
            ensure_ascii=False,
        )
    )
'@

$SmokeCode | python -
