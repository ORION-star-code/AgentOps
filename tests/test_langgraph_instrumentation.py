import pytest

from agentops_api import AgentOpsClient, LangGraphInstrumentation
from conftest import TEST_API_KEY, TEST_PROJECT_ID


class _TestClientAdapter:
    def __init__(self, client) -> None:
        self.client = client

    def request(self, method, url, *, json=None, params=None, headers=None):
        return self.client.request(method, url, json=json, params=params, headers=headers)


class _FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        self.value += 0.05
        return self.value


def _sdk(make_client) -> AgentOpsClient:
    return AgentOpsClient(
        base_url="http://testserver",
        api_key=TEST_API_KEY,
        project_id=TEST_PROJECT_ID,
        http_client=_TestClientAdapter(make_client(include_auth_header=False)),
    )


def test_langgraph_trace_run_records_node_model_tool_and_completes(make_client) -> None:
    sdk = _sdk(make_client)
    instrumentation = LangGraphInstrumentation(sdk, clock=_FakeClock())

    with instrumentation.trace_run(name="Fake LangGraph run") as run:
        run_id = run.run_id
        run.record_message("user", "Who does the policy apply to?")
        with run.node("retrieve_documents", metadata={"graph_step": 1}):
            run.record_tool_call(
                tool_name="vector_search",
                arguments={"query": "policy applies to"},
                result={"chunk_ids": ["chunk-001"]},
                latency_ms=128,
                token_count=42,
            )
        with run.node("answer_question", metadata={"graph_step": 2}):
            run.record_model_call(
                model_name="mimo-v2.5-pro",
                prompt="Answer with citations.",
                response="The policy applies to enterprise users.",
                latency_ms=240,
                token_count=120,
            )

    detail = sdk.get_run_detail(run_id)

    assert detail["run"]["status"] == "succeeded"
    assert detail["summary"]["message_count"] == 1
    assert detail["summary"]["tool_call_count"] == 1
    assert detail["summary"]["model_call_count"] == 1
    assert detail["summary"]["event_count"] == 5
    assert detail["summary"]["total_tokens"] == 162
    assert detail["summary"]["total_latency_ms"] == 468
    assert [event["name"] for event in detail["timeline"]] == [
        "langgraph_message",
        "langgraph_tool_call",
        "langgraph_node",
        "langgraph_model_call",
        "langgraph_node",
    ]
    node_events = [event for event in detail["timeline"] if event["name"] == "langgraph_node"]
    assert [event["payload"]["node_name"] for event in node_events] == [
        "retrieve_documents",
        "answer_question",
    ]
    assert all(event["payload"]["status"] == "succeeded" for event in node_events)


def test_langgraph_wrap_node_records_node_event(make_client) -> None:
    sdk = _sdk(make_client)
    instrumentation = LangGraphInstrumentation(sdk, clock=_FakeClock())
    run = sdk.create_run(name="Existing LangGraph run")
    recorder = instrumentation.attach_run(run["id"])

    def fake_node(state: dict) -> dict:
        return {"answer": state["question"].upper()}

    wrapped = recorder.wrap_node("answer_question", fake_node, metadata={"kind": "node"})
    result = wrapped({"question": "hello"})

    sdk.complete_run(run["id"])
    detail = sdk.get_run_detail(run["id"])

    assert result == {"answer": "HELLO"}
    assert detail["summary"]["event_count"] == 1
    assert detail["timeline"][0]["name"] == "langgraph_node"
    assert detail["timeline"][0]["payload"]["node_name"] == "answer_question"
    assert detail["timeline"][0]["payload"]["metadata"] == {"kind": "node"}


def test_langgraph_node_error_records_error_and_fails_run(make_client) -> None:
    sdk = _sdk(make_client)
    instrumentation = LangGraphInstrumentation(sdk, clock=_FakeClock())
    run_id = ""

    with pytest.raises(RuntimeError, match="retriever failed"):
        with instrumentation.trace_run(name="Failing LangGraph run") as run:
            run_id = run.run_id
            with run.node("retrieve_documents"):
                raise RuntimeError("retriever failed")

    detail = sdk.get_run_detail(run_id)

    assert detail["run"]["status"] == "failed"
    assert detail["summary"]["event_count"] == 2
    assert detail["summary"]["error_count"] == 1
    assert detail["timeline"][0]["name"] == "langgraph_node"
    assert detail["timeline"][0]["payload"]["status"] == "failed"
    assert detail["errors"][0]["payload"]["node_name"] == "retrieve_documents"
    assert detail["errors"][0]["payload"]["error_type"] == "RuntimeError"
    assert detail["errors"][0]["payload"]["message"] == "retriever failed"


def test_langgraph_attached_run_can_record_custom_event_without_closing_run(make_client) -> None:
    sdk = _sdk(make_client)
    run = sdk.create_run(name="Attached run")
    recorder = LangGraphInstrumentation(sdk).attach_run(run["id"])

    recorder.record_custom("langgraph_checkpoint", {"checkpoint_id": "cp-001"})

    detail = sdk.get_run_detail(run["id"])
    assert detail["run"]["status"] == "running"
    assert detail["timeline"][0]["payload"]["instrumentation"] == "langgraph"
    assert detail["timeline"][0]["payload"]["checkpoint_id"] == "cp-001"
