import json

import httpx
import pytest

from agentops_api.sdk import AgentOpsAPIError, AgentOpsClient
from conftest import TEST_API_KEY, TEST_PROJECT_ID


class _TestClientAdapter:
    def __init__(self, client) -> None:
        self.client = client
        self.requests = []
        self.closed = False

    def request(self, method, url, *, json=None, params=None, headers=None):
        self.requests.append(
            {
                "method": method,
                "url": url,
                "json": json,
                "params": params,
                "headers": headers,
            }
        )
        return self.client.request(method, url, json=json, params=params, headers=headers)

    def close(self) -> None:
        self.closed = True


def test_sdk_sends_api_key_and_default_project_id() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": "run-001",
                "project_id": "demo-project",
                "session_id": None,
                "name": "SDK smoke",
                "status": "running",
                "started_at": "2026-05-30T12:00:00Z",
                "ended_at": None,
                "metadata": {},
            },
        )

    http_client = httpx.Client(
        base_url="http://agentops.test",
        transport=httpx.MockTransport(handler),
    )
    sdk = AgentOpsClient(
        base_url="http://agentops.test",
        api_key="sdk-test-key",
        project_id="demo-project",
        http_client=http_client,
    )

    run = sdk.create_run(name="SDK smoke")

    assert run["id"] == "run-001"
    assert captured["headers"]["x-agentops-api-key"] == "sdk-test-key"
    assert captured["body"]["project_id"] == "demo-project"
    assert captured["body"]["name"] == "SDK smoke"


def test_sdk_raises_api_error_without_exposing_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "API key cannot access this project"})

    sdk = AgentOpsClient(
        base_url="http://agentops.test",
        api_key="super-secret-sdk-key",
        project_id="demo-project",
        http_client=httpx.Client(
            base_url="http://agentops.test",
            transport=httpx.MockTransport(handler),
        ),
    )

    with pytest.raises(AgentOpsAPIError) as exc_info:
        sdk.create_run(project_id="other-project")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "API key cannot access this project"
    assert "super-secret-sdk-key" not in str(exc_info.value)


def test_sdk_writes_complete_run_lifecycle(make_client) -> None:
    api_client = make_client(include_auth_header=False)
    sdk = AgentOpsClient(
        base_url="http://testserver",
        api_key=TEST_API_KEY,
        project_id=TEST_PROJECT_ID,
        http_client=_TestClientAdapter(api_client),
    )

    run = sdk.create_run(name="SDK lifecycle", metadata={"agent_framework": "langgraph"})
    run_id = run["id"]
    message = sdk.append_event(
        run_id,
        "message",
        name="user_message",
        payload={"role": "user", "content": "Who does the policy apply to?"},
    )
    rag = sdk.append_rag_evidence(
        run_id,
        {
            "query": "policy applies to",
            "hit_status": "hit",
            "chunks": [
                {
                    "chunk_id": "chunk-001",
                    "source_uri": "policy.md",
                    "content_preview": "The policy applies to enterprise users.",
                    "score": 0.92,
                }
            ],
            "citations": [
                {
                    "chunk_id": "chunk-001",
                    "claim": "The policy applies to enterprise users.",
                    "quote": "The policy applies to enterprise users.",
                }
            ],
            "citation_coverage": 1.0,
        },
    )
    evaluation = sdk.append_evaluation(
        run_id,
        {
            "answer": "The policy applies to enterprise users.",
            "rag_event_id": rag["id"],
            "metrics": [
                {"name": "groundedness", "score": 0.9},
                {"name": "hallucination_risk", "score": 0.05},
            ],
        },
    )
    completed = sdk.complete_run(run_id)
    detail = sdk.get_run_detail(run_id)
    events = sdk.list_events(run_id, limit=10)

    assert message["sequence"] == 1
    assert evaluation["payload"]["verdict"] == "pass"
    assert completed["status"] == "succeeded"
    assert detail["summary"]["event_count"] == 3
    assert [event["sequence"] for event in events] == [1, 2, 3]


def test_sdk_runs_golden_dataset_and_compares_regression(make_client) -> None:
    sdk = AgentOpsClient(
        base_url="http://testserver",
        api_key=TEST_API_KEY,
        project_id=TEST_PROJECT_ID,
        http_client=_TestClientAdapter(make_client(include_auth_header=False)),
    )
    dataset = {
        "dataset_id": "rag-trust-suite",
        "version": "2026.05.30",
        "cases": [
            {
                "case_id": "case-001",
                "user_input": "Who does the policy apply to?",
                "reference_context": ["The policy applies to enterprise users."],
                "expected_answer": "The policy applies to enterprise users.",
                "judge_rubric": "Answer must be grounded.",
                "pass_criteria": "All metrics pass.",
            }
        ],
    }

    baseline = sdk.run_golden_dataset(dataset, metadata={"version": "baseline"})
    candidate = sdk.run_golden_dataset(dataset, metadata={"version": "candidate"})
    regression = sdk.compare_golden_dataset_runs(
        baseline_run_id=baseline["run_id"],
        candidate_run_id=candidate["run_id"],
        baseline_version="baseline",
        candidate_version="candidate",
    )

    assert baseline["passed_cases"] == 1
    assert regression["status"] == "unchanged"
    assert regression["total_cases"] == 1
    persisted_report = sdk.get_regression_report(regression["case_reports"][0]["report_id"])
    assert persisted_report["status"] == "unchanged"
