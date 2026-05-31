import json
import sqlite3
from datetime import UTC, datetime, timedelta

from agentops_api.observability import AgentRunCreate, RunEventCreate, RunEventType, TraceRepository
from agentops_api.privacy import RetentionConfig
from agentops_api.retention import main as retention_main


def test_retention_cleanup_dry_run_and_execute_delete_only_expired_terminal_runs(tmp_path) -> None:
    db_path = tmp_path / "agentops.db"
    repository = TraceRepository(db_path, retention_config=RetentionConfig(days=7))
    now = datetime(2026, 5, 31, tzinfo=UTC)
    expired_run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    fresh_run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    running_run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    repository.append_event(
        expired_run.id,
        RunEventCreate(
            type=RunEventType.MESSAGE,
            payload={"content": "expired"},
        ),
    )
    repository.append_event(
        fresh_run.id,
        RunEventCreate(
            type=RunEventType.MESSAGE,
            payload={"content": "fresh"},
        ),
    )
    repository.append_event(
        running_run.id,
        RunEventCreate(
            type=RunEventType.MESSAGE,
            payload={"content": "active"},
        ),
    )
    repository.complete_run(expired_run.id)
    repository.complete_run(fresh_run.id)
    _set_run_dates(
        db_path,
        expired_run.id,
        started_at=now - timedelta(days=30),
        ended_at=now - timedelta(days=20),
    )
    _set_run_dates(
        db_path,
        fresh_run.id,
        started_at=now - timedelta(days=2),
        ended_at=now - timedelta(days=1),
    )
    _set_run_dates(
        db_path,
        running_run.id,
        started_at=now - timedelta(days=30),
        ended_at=None,
    )

    dry_run = repository.cleanup_expired_runs(dry_run=True, now=now)

    assert dry_run.expired_run_count == 1
    assert dry_run.expired_event_count == 1
    assert dry_run.deleted_run_count == 0
    assert dry_run.skipped_running_count == 1
    assert repository.get_run(expired_run.id) is not None

    execute = repository.cleanup_expired_runs(dry_run=False, now=now)

    assert execute.expired_run_count == 1
    assert execute.expired_event_count == 1
    assert execute.deleted_run_count == 1
    assert execute.deleted_event_count == 1
    assert execute.skipped_running_count == 1
    assert repository.get_run(expired_run.id) is None
    assert repository.get_run(fresh_run.id) is not None
    assert repository.get_run(running_run.id) is not None
    assert repository.list_events(running_run.id) != []


def test_retention_cleanup_is_noop_when_retention_is_disabled(tmp_path) -> None:
    repository = TraceRepository(tmp_path / "agentops.db")
    run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    repository.complete_run(run.id)

    result = repository.cleanup_expired_runs(dry_run=False)

    assert result.retention_days is None
    assert result.expired_run_count == 0
    assert result.deleted_run_count == 0
    assert repository.get_run(run.id) is not None


def test_retention_cli_outputs_dry_run_json(tmp_path, capsys) -> None:
    db_path = tmp_path / "agentops.db"
    repository = TraceRepository(db_path, retention_config=RetentionConfig(days=1))
    run = repository.create_run(AgentRunCreate(project_id="demo-project"))
    repository.complete_run(run.id)
    now = datetime.now(UTC)
    _set_run_dates(
        db_path,
        run.id,
        started_at=now - timedelta(days=4),
        ended_at=now - timedelta(days=3),
    )

    exit_code = retention_main(
        [
            "--db-path",
            str(db_path),
            "--retention-days",
            "1",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["enabled"] is True
    assert output["mode"] == "dry-run"
    assert output["expired_run_count"] == 1
    assert output["deleted_run_count"] == 0
    assert repository.get_run(run.id) is not None


def _set_run_dates(
    db_path,
    run_id: str,
    *,
    started_at: datetime,
    ended_at: datetime | None,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE runs
            SET started_at = ?, ended_at = ?
            WHERE id = ?
            """,
            (
                started_at.isoformat(),
                ended_at.isoformat() if ended_at else None,
                run_id,
            ),
        )
