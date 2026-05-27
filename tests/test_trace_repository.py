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
