from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from agentops_api.observability import (
    AgentRunCreate,
    RunAlreadyEndedError,
    RunEventCreate,
    RunEventType,
    RunNotFoundError,
    RunStatus,
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


def test_concurrent_appends_generate_unique_sequences(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")
    run = repository.create_run(AgentRunCreate(project_id="demo-project"))

    def append_event(index: int) -> int:
        event = repository.append_event(
            run.id,
            RunEventCreate(
                type=RunEventType.CUSTOM,
                name=f"event-{index}",
                payload={"index": index},
            ),
        )
        return event.sequence

    with ThreadPoolExecutor(max_workers=8) as executor:
        sequences = list(executor.map(append_event, range(20)))

    events = repository.list_events(run.id)
    assert sorted(sequences) == list(range(1, 21))
    assert [event.sequence for event in events] == list(range(1, 21))


def test_list_events_supports_limit_cursor_and_type_filter(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")
    run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    event_types = [
        RunEventType.MESSAGE,
        RunEventType.TOOL_CALL,
        RunEventType.MESSAGE,
        RunEventType.ERROR,
        RunEventType.MESSAGE,
    ]
    for index, event_type in enumerate(event_types, start=1):
        repository.append_event(
            run.id,
            RunEventCreate(
                type=event_type,
                name=f"event-{index}",
                payload={"token_count": index, "latency_ms": index * 10},
            ),
        )

    first_page = repository.list_events(run.id, limit=2)
    second_page = repository.list_events(run.id, limit=2, after_sequence=2)
    messages = repository.list_events(run.id, event_type=RunEventType.MESSAGE)
    summary = repository.get_event_summary(run.id)

    assert [event.sequence for event in first_page] == [1, 2]
    assert [event.sequence for event in second_page] == [3, 4]
    assert [event.sequence for event in messages] == [1, 3, 5]
    assert summary.event_count == 5
    assert summary.message_count == 3
    assert summary.tool_call_count == 1
    assert summary.error_count == 1
    assert summary.total_tokens == 15
    assert summary.total_latency_ms == 150


def test_list_recent_events_returns_latest_page_in_sequence_order(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")
    run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    for index in range(1, 6):
        repository.append_event(
            run.id,
            RunEventCreate(
                type=RunEventType.CUSTOM,
                name=f"event-{index}",
                payload={"index": index},
            ),
        )

    recent = repository.list_recent_events(run.id, limit=3)

    assert [event.sequence for event in recent] == [3, 4, 5]


def test_finishing_run_sets_status_and_ended_at(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")
    complete_run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    failed_run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    canceled_run = repository.create_run(AgentRunCreate(project_id="demo-project"))

    completed = repository.complete_run(complete_run.id)
    failed = repository.fail_run(failed_run.id)
    canceled = repository.cancel_run(canceled_run.id)

    assert completed.status == RunStatus.SUCCEEDED
    assert completed.ended_at is not None
    assert failed.status == RunStatus.FAILED
    assert failed.ended_at is not None
    assert canceled.status == RunStatus.CANCELED
    assert canceled.ended_at is not None


def test_finished_run_rejects_lifecycle_and_event_writes(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")
    run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    repository.complete_run(run.id)

    with pytest.raises(RunAlreadyEndedError):
        repository.complete_run(run.id)

    with pytest.raises(RunAlreadyEndedError):
        repository.append_event(
            run.id,
            RunEventCreate(type=RunEventType.MESSAGE, payload={"role": "user"}),
        )


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
