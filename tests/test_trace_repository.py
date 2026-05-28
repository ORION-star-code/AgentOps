import pytest
from pydantic import ValidationError

from agentops_api.observability import (
    AgentRunCreate,
    RunEventCreate,
    RunEventType,
    RunNotFoundError,
    TraceRepository,
)


def test_sqlite_repository_creates_and_fetches_run(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")

    run = repository.create_run(
        AgentRunCreate(
            project_id="demo-project",
            session_id="session-001",
            name="RAG answer debug run",
            metadata={"agent_framework": "langgraph"},
        )
    )

    fetched = repository.get_run(run.id)
    assert fetched is not None
    assert fetched.id == run.id
    assert fetched.project_id == "demo-project"
    assert fetched.metadata == {"agent_framework": "langgraph"}


def test_appending_events_generates_stable_sequences(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")
    run = repository.create_run(AgentRunCreate(project_id="demo-project"))

    first = repository.append_event(
        run.id,
        RunEventCreate(type=RunEventType.MESSAGE, name="input", payload={"role": "user"}),
    )
    second = repository.append_event(
        run.id,
        RunEventCreate(type=RunEventType.TOOL_CALL, name="retrieve_documents"),
    )

    events = repository.list_events(run.id)
    assert first.sequence == 1
    assert second.sequence == 2
    assert [event.sequence for event in events] == [1, 2]
    assert [event.id for event in events] == [first.id, second.id]


def test_repository_redacts_run_metadata_before_persistence(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")

    run = repository.create_run(
        AgentRunCreate(
            project_id="demo-project",
            metadata={
                "agent_framework": "langgraph",
                "api_key": "sk-live-secret",
                "nested": {"password": "do-not-store"},
            },
        )
    )
    fetched = repository.get_run(run.id)

    assert fetched is not None
    assert fetched.metadata["agent_framework"] == "langgraph"
    assert fetched.metadata["api_key"] == "[REDACTED]"
    assert fetched.metadata["nested"]["password"] == "[REDACTED]"
    assert fetched.metadata["_agentops_redaction"]["redaction_count"] == 2
    assert "sk-live-secret" not in str(fetched.metadata)
    assert "do-not-store" not in str(fetched.metadata)


def test_repository_redacts_event_payload_before_persistence(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")
    run = repository.create_run(AgentRunCreate(project_id="demo-project"))

    event = repository.append_event(
        run.id,
        RunEventCreate(
            type=RunEventType.TOOL_CALL,
            payload={
                "tool_name": "vector_search",
                "token_count": 42,
                "headers": {"authorization": "Bearer secret"},
            },
        ),
    )
    events = repository.list_events(run.id)

    assert event.payload["token_count"] == 42
    assert events[0].payload["headers"]["authorization"] == "[REDACTED]"
    assert events[0].payload["_agentops_redaction"] == {
        "redaction_count": 1,
        "redacted_fields": ["payload.headers.authorization"],
    }
    assert "Bearer secret" not in str(events[0].payload)


def test_unknown_run_event_append_fails(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")

    with pytest.raises(RunNotFoundError):
        repository.append_event(
            "missing-run",
            RunEventCreate(type=RunEventType.ERROR, payload={"message": "not found"}),
        )


def test_metadata_and_payload_size_are_limited() -> None:
    oversized = {"text": "x" * (64 * 1024)}

    with pytest.raises(ValidationError):
        AgentRunCreate(project_id="demo-project", metadata=oversized)

    with pytest.raises(ValidationError):
        RunEventCreate(type=RunEventType.CUSTOM, payload=oversized)
