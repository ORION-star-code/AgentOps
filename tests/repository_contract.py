"""Reusable storage adapter contract checks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest

from agentops_api.audit import AuditEvent, AuditOutcome
from agentops_api.evaluation import RegressionComparisonCreate, build_regression_report
from agentops_api.observability import (
    AgentRunCreate,
    RunAlreadyEndedError,
    RunEventCreate,
    RunEventType,
    RunNotFoundError,
    RunStatus,
    TraceRepositoryProtocol,
)
from agentops_api.observability.schemas import now_utc


RepositoryFactory = Callable[[], TraceRepositoryProtocol]


def assert_trace_repository_contract(make_repository: RepositoryFactory) -> None:
    """Run the storage contract every trace repository adapter must satisfy."""

    _assert_run_crud_and_project_listing(make_repository())
    _assert_event_append_query_summary_and_paging(make_repository())
    _assert_terminal_lifecycle_rules(make_repository())
    _assert_regression_report_persistence(make_repository())
    _assert_audit_event_persistence(make_repository())
    _assert_retention_cleanup_contract(make_repository())


def _assert_run_crud_and_project_listing(repository: TraceRepositoryProtocol) -> None:
    first = repository.create_run(
        AgentRunCreate(
            project_id="demo-project",
            session_id="session-001",
            name="contract run",
            metadata={"agent_framework": "langgraph"},
        )
    )
    second = repository.create_run(AgentRunCreate(project_id="demo-project", name="second"))
    other = repository.create_run(AgentRunCreate(project_id="other-project"))
    repository.complete_run(first.id)

    fetched = repository.get_run(first.id)
    assert fetched is not None
    assert fetched.id == first.id
    assert fetched.metadata["agent_framework"] == "langgraph"

    project_runs = repository.list_runs("demo-project", limit=10)
    succeeded_runs = repository.list_runs(
        "demo-project",
        limit=10,
        status=RunStatus.SUCCEEDED,
    )
    summary_items = repository.list_runs_with_summaries("demo-project", limit=10)

    assert {run.id for run in project_runs} == {first.id, second.id}
    assert other.id not in {run.id for run in project_runs}
    assert [run.id for run in succeeded_runs] == [first.id]
    assert {item.id for item in summary_items} == {first.id, second.id}


def _assert_event_append_query_summary_and_paging(repository: TraceRepositoryProtocol) -> None:
    run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    for index, event_type in enumerate(
        [
            RunEventType.MESSAGE,
            RunEventType.TOOL_CALL,
            RunEventType.MESSAGE,
            RunEventType.ERROR,
        ],
        start=1,
    ):
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
    recent = repository.list_recent_events(run.id, limit=2)
    summary = repository.get_event_summary(run.id)

    assert [event.sequence for event in first_page] == [1, 2]
    assert [event.sequence for event in second_page] == [3, 4]
    assert [event.sequence for event in messages] == [1, 3]
    assert [event.sequence for event in recent] == [3, 4]
    assert summary.event_count == 4
    assert summary.message_count == 2
    assert summary.tool_call_count == 1
    assert summary.error_count == 1
    assert summary.total_tokens == 10
    assert summary.total_latency_ms == 100

    with pytest.raises(RunNotFoundError):
        repository.list_events("missing-run")


def _assert_terminal_lifecycle_rules(repository: TraceRepositoryProtocol) -> None:
    completed_run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    failed_run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    canceled_run = repository.create_run(AgentRunCreate(project_id="demo-project"))

    completed = repository.complete_run(completed_run.id)
    failed = repository.fail_run(failed_run.id)
    canceled = repository.cancel_run(canceled_run.id)

    assert completed.status == RunStatus.SUCCEEDED
    assert completed.ended_at is not None
    assert failed.status == RunStatus.FAILED
    assert canceled.status == RunStatus.CANCELED

    with pytest.raises(RunAlreadyEndedError):
        repository.append_event(
            completed_run.id,
            RunEventCreate(type=RunEventType.MESSAGE, payload={"role": "user"}),
        )


def _assert_regression_report_persistence(repository: TraceRepositoryProtocol) -> None:
    report = build_regression_report(
        RegressionComparisonCreate(
            baseline={
                "run_id": "baseline-run",
                "version": "v1",
                "evaluation": {
                    "answer": "Grounded answer.",
                    "metrics": [{"name": "trustworthiness", "score": 0.7}],
                },
            },
            candidate={
                "run_id": "candidate-run",
                "version": "v2",
                "evaluation": {
                    "answer": "Grounded answer.",
                    "metrics": [{"name": "trustworthiness", "score": 0.9}],
                },
            },
        ),
        project_id="demo-project",
        report_id="contract-report",
    )

    repository.save_regression_report(report)
    fetched = repository.get_regression_report("contract-report")

    assert fetched is not None
    assert fetched.project_id == "demo-project"
    assert fetched.status == report.status


def _assert_audit_event_persistence(repository: TraceRepositoryProtocol) -> None:
    event = AuditEvent(
        project_id="demo-project",
        key_id="key-001",
        scope="read",
        method="GET",
        path="/v1/runs",
        status_code=200,
        outcome=AuditOutcome.SUCCEEDED,
        reason="request_completed",
    )

    repository.save_audit_event(event)
    events = repository.list_audit_events(project_id="demo-project", limit=10)

    assert len(events) == 1
    assert events[0].id == event.id
    assert events[0].key_id == "key-001"
    assert events[0].path == "/v1/runs"


def _assert_retention_cleanup_contract(repository: TraceRepositoryProtocol) -> None:
    run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    repository.append_event(
        run.id,
        RunEventCreate(type=RunEventType.CUSTOM, payload={"kind": "retention"}),
    )
    repository.complete_run(run.id)

    dry_run = repository.cleanup_expired_runs(dry_run=True, now=now_utc() + timedelta(days=3650))

    assert dry_run.dry_run is True
    assert dry_run.deleted_run_count == 0
    assert repository.get_run(run.id) is not None
