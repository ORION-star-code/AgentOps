"""SQLite-backed trace event repository."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from agentops_api.audit import AuditEvent, AuditOutcome
from agentops_api.observability.schemas import (
    AgentRun,
    AgentRunCreate,
    AgentRunListItem,
    RunEvent,
    RunEventCreate,
    RunDetailSummary,
    RunEventType,
    RunStatus,
    now_utc,
)
from agentops_api.privacy import RetentionConfig, redact_json_object

if TYPE_CHECKING:
    from agentops_api.evaluation import RegressionReport

DEFAULT_DB_PATH = Path(".agentops") / "agentops.db"


class RunNotFoundError(LookupError):
    """Raised when a run-scoped operation targets an unknown run."""


class RunAlreadyEndedError(RuntimeError):
    """Raised when a write targets a run that has already ended."""


@dataclass(frozen=True)
class RetentionCleanupResult:
    """Outcome of one retention cleanup pass."""

    retention_days: int | None
    cutoff: datetime | None
    dry_run: bool
    expired_run_count: int
    expired_event_count: int
    deleted_run_count: int
    deleted_event_count: int
    skipped_running_count: int
    expired_run_ids: tuple[str, ...]


class TraceRepository:
    """Persist Agent runs and append-only timeline events in SQLite."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        retention_config: RetentionConfig | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.retention_config = retention_config or RetentionConfig()
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    session_id TEXT,
                    name TEXT,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    metadata TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    name TEXT,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE(run_id, sequence)
                );

                CREATE INDEX IF NOT EXISTS idx_run_events_run_sequence
                    ON run_events (run_id, sequence);

                CREATE TABLE IF NOT EXISTS regression_reports (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    baseline_run_id TEXT NOT NULL,
                    candidate_run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    report TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_regression_reports_project_created
                    ON regression_reports (project_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_regression_reports_runs
                    ON regression_reports (baseline_run_id, candidate_run_id);

                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    key_id TEXT,
                    scope TEXT,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    reason TEXT,
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_events_project_timestamp
                    ON audit_events (project_id, timestamp);

                CREATE INDEX IF NOT EXISTS idx_audit_events_key_timestamp
                    ON audit_events (key_id, timestamp);
                """
            )

    def create_run(self, payload: AgentRunCreate) -> AgentRun:
        metadata = redact_json_object(payload.metadata, path_prefix="metadata").value
        run = AgentRun(
            id=str(uuid4()),
            project_id=payload.project_id,
            session_id=payload.session_id,
            name=payload.name,
            status=RunStatus.RUNNING,
            started_at=now_utc(),
            ended_at=None,
            metadata=metadata,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, project_id, session_id, name, status, started_at, ended_at, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.project_id,
                    run.session_id,
                    run.name,
                    run.status.value,
                    run.started_at.isoformat(),
                    run.ended_at.isoformat() if run.ended_at else None,
                    _to_json(run.metadata),
                ),
            )
        return run

    def get_run(self, run_id: str) -> AgentRun | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_run(row)

    def list_runs(
        self,
        project_id: str,
        *,
        limit: int,
        status: RunStatus | None = None,
    ) -> list[AgentRun]:
        conditions = ["project_id = ?"]
        parameters: list[Any] = [project_id]
        if status is not None:
            conditions.append("status = ?")
            parameters.append(status.value)

        query = f"""
            SELECT *
            FROM runs
            WHERE {" AND ".join(conditions)}
            ORDER BY started_at DESC, id DESC
            LIMIT ?
        """
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_row_to_run(row) for row in rows]

    def list_runs_with_summaries(
        self,
        project_id: str,
        *,
        limit: int,
        status: RunStatus | None = None,
    ) -> list[AgentRunListItem]:
        conditions = ["project_id = ?"]
        parameters: list[Any] = [project_id]
        if status is not None:
            conditions.append("status = ?")
            parameters.append(status.value)

        query = f"""
            WITH selected_runs AS (
                SELECT *
                FROM runs
                WHERE {" AND ".join(conditions)}
                ORDER BY started_at DESC, id DESC
                LIMIT ?
            )
            SELECT
                selected_runs.*,
                COUNT(run_events.id) AS event_count,
                SUM(CASE WHEN run_events.type = 'message' THEN 1 ELSE 0 END)
                    AS message_count,
                SUM(CASE WHEN run_events.type = 'model_call' THEN 1 ELSE 0 END)
                    AS model_call_count,
                SUM(CASE WHEN run_events.type = 'tool_call' THEN 1 ELSE 0 END)
                    AS tool_call_count,
                SUM(CASE WHEN run_events.type = 'rag_retrieval' THEN 1 ELSE 0 END)
                    AS rag_retrieval_count,
                SUM(CASE WHEN run_events.type = 'evaluation' THEN 1 ELSE 0 END)
                    AS evaluation_count,
                SUM(CASE WHEN run_events.type = 'error' THEN 1 ELSE 0 END)
                    AS error_count,
                SUM(
                    COALESCE(
                        json_extract(run_events.payload, '$.token_count'),
                        json_extract(run_events.payload, '$.usage.token_count'),
                        0
                    )
                ) AS total_tokens,
                SUM(
                    COALESCE(
                        json_extract(run_events.payload, '$.latency_ms'),
                        json_extract(run_events.payload, '$.usage.latency_ms'),
                        0
                    )
                ) AS total_latency_ms
            FROM selected_runs
            LEFT JOIN run_events ON run_events.run_id = selected_runs.id
            GROUP BY
                selected_runs.id,
                selected_runs.project_id,
                selected_runs.session_id,
                selected_runs.name,
                selected_runs.status,
                selected_runs.started_at,
                selected_runs.ended_at,
                selected_runs.metadata
            ORDER BY selected_runs.started_at DESC, selected_runs.id DESC
        """
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_row_to_run_list_item(row) for row in rows]

    def append_event(self, run_id: str, payload: RunEventCreate) -> RunEvent:
        redacted_payload = redact_json_object(payload.payload, path_prefix="payload").value
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            run_row = connection.execute(
                "SELECT status FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                raise RunNotFoundError(run_id)
            if RunStatus(run_row["status"]) != RunStatus.RUNNING:
                raise RunAlreadyEndedError(run_id)

            next_sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            event = RunEvent(
                id=str(uuid4()),
                run_id=run_id,
                sequence=next_sequence,
                type=payload.type,
                name=payload.name,
                timestamp=now_utc(),
                payload=redacted_payload,
            )
            connection.execute(
                """
                INSERT INTO run_events (
                    id, run_id, sequence, type, name, timestamp, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.run_id,
                    event.sequence,
                    event.type.value,
                    event.name,
                    event.timestamp.isoformat(),
                    _to_json(event.payload),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return event

    def list_events(
        self,
        run_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
        event_type: RunEventType | None = None,
    ) -> list[RunEvent]:
        if self.get_run(run_id) is None:
            raise RunNotFoundError(run_id)
        conditions = ["run_id = ?"]
        parameters: list[Any] = [run_id]
        if after_sequence is not None:
            conditions.append("sequence > ?")
            parameters.append(after_sequence)
        if event_type is not None:
            conditions.append("type = ?")
            parameters.append(event_type.value)

        query = f"""
            SELECT * FROM run_events
            WHERE {" AND ".join(conditions)}
            ORDER BY sequence ASC
        """
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_recent_events(self, run_id: str, *, limit: int) -> list[RunEvent]:
        if self.get_run(run_id) is None:
            raise RunNotFoundError(run_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM (
                    SELECT * FROM run_events
                    WHERE run_id = ?
                    ORDER BY sequence DESC
                    LIMIT ?
                )
                ORDER BY sequence ASC
                """,
                (run_id, limit),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def get_event_summary(self, run_id: str) -> RunDetailSummary:
        if self.get_run(run_id) is None:
            raise RunNotFoundError(run_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS event_count,
                    SUM(CASE WHEN type = 'message' THEN 1 ELSE 0 END) AS message_count,
                    SUM(CASE WHEN type = 'model_call' THEN 1 ELSE 0 END) AS model_call_count,
                    SUM(CASE WHEN type = 'tool_call' THEN 1 ELSE 0 END) AS tool_call_count,
                    SUM(CASE WHEN type = 'rag_retrieval' THEN 1 ELSE 0 END)
                        AS rag_retrieval_count,
                    SUM(CASE WHEN type = 'evaluation' THEN 1 ELSE 0 END) AS evaluation_count,
                    SUM(CASE WHEN type = 'error' THEN 1 ELSE 0 END) AS error_count,
                    SUM(
                        COALESCE(
                            json_extract(payload, '$.token_count'),
                            json_extract(payload, '$.usage.token_count'),
                            0
                        )
                    ) AS total_tokens,
                    SUM(
                        COALESCE(
                            json_extract(payload, '$.latency_ms'),
                            json_extract(payload, '$.usage.latency_ms'),
                            0
                        )
                    ) AS total_latency_ms
                FROM run_events
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        return RunDetailSummary(
            event_count=row["event_count"] or 0,
            message_count=row["message_count"] or 0,
            model_call_count=row["model_call_count"] or 0,
            tool_call_count=row["tool_call_count"] or 0,
            rag_retrieval_count=row["rag_retrieval_count"] or 0,
            evaluation_count=row["evaluation_count"] or 0,
            error_count=row["error_count"] or 0,
            total_tokens=row["total_tokens"] or 0,
            total_latency_ms=row["total_latency_ms"] or 0,
        )

    def complete_run(self, run_id: str) -> AgentRun:
        return self._finish_run(run_id, RunStatus.SUCCEEDED)

    def fail_run(self, run_id: str) -> AgentRun:
        return self._finish_run(run_id, RunStatus.FAILED)

    def cancel_run(self, run_id: str) -> AgentRun:
        return self._finish_run(run_id, RunStatus.CANCELED)

    def save_regression_report(self, report: RegressionReport) -> RegressionReport:
        """Persist a reproducible regression comparison report."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO regression_reports (
                    id,
                    project_id,
                    created_at,
                    baseline_run_id,
                    candidate_run_id,
                    status,
                    report
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    report.project_id,
                    report.created_at.isoformat(),
                    report.baseline_run_id,
                    report.candidate_run_id,
                    report.status.value,
                    _to_json(report.model_dump(mode="json")),
                ),
            )
        return report

    def get_regression_report(self, report_id: str) -> RegressionReport | None:
        """Fetch a persisted regression comparison report by ID."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT report FROM regression_reports WHERE id = ?",
                (report_id,),
            ).fetchone()
        if row is None:
            return None

        from agentops_api.evaluation import RegressionReport

        return RegressionReport.model_validate(_from_json(row["report"]))

    def save_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Persist a non-sensitive API audit event."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    id,
                    project_id,
                    key_id,
                    scope,
                    method,
                    path,
                    status_code,
                    outcome,
                    reason,
                    timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.project_id,
                    event.key_id,
                    event.scope,
                    event.method,
                    event.path,
                    event.status_code,
                    event.outcome.value,
                    event.reason,
                    event.timestamp.isoformat(),
                ),
            )
        return event

    def list_audit_events(
        self,
        *,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Return recent audit events, optionally scoped to a project."""

        conditions: list[str] = []
        parameters: list[Any] = []
        if project_id is not None:
            conditions.append("project_id = ?")
            parameters.append(project_id)

        query = "SELECT * FROM audit_events"
        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"
        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_row_to_audit_event(row) for row in rows]

    def cleanup_expired_runs(
        self,
        *,
        dry_run: bool = True,
        now: datetime | None = None,
    ) -> RetentionCleanupResult:
        """Delete terminal runs older than the configured retention window."""

        if not self.retention_config.enabled:
            return RetentionCleanupResult(
                retention_days=None,
                cutoff=None,
                dry_run=dry_run,
                expired_run_count=0,
                expired_event_count=0,
                deleted_run_count=0,
                deleted_event_count=0,
                skipped_running_count=0,
                expired_run_ids=(),
            )

        retention_days = self.retention_config.days
        if retention_days is None:
            raise ValueError("retention cleanup requires configured retention days")
        current_time = now or now_utc()
        cutoff = current_time - timedelta(days=retention_days)
        cutoff_iso = cutoff.isoformat()

        connection = self._connect()
        try:
            expired_rows = connection.execute(
                """
                SELECT id
                FROM runs
                WHERE status != ?
                    AND ended_at IS NOT NULL
                    AND ended_at < ?
                ORDER BY ended_at ASC, id ASC
                """,
                (RunStatus.RUNNING.value, cutoff_iso),
            ).fetchall()
            expired_run_ids = tuple(row["id"] for row in expired_rows)
            skipped_running_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM runs
                WHERE status = ?
                    AND started_at < ?
                """,
                (RunStatus.RUNNING.value, cutoff_iso),
            ).fetchone()[0]
            expired_event_count = self._count_events_for_run_ids(connection, expired_run_ids)

            deleted_run_count = 0
            deleted_event_count = 0
            if not dry_run and expired_run_ids:
                connection.execute("BEGIN IMMEDIATE")
                expired_event_count = self._count_events_for_run_ids(connection, expired_run_ids)
                placeholders = ",".join("?" for _ in expired_run_ids)
                connection.execute(
                    f"DELETE FROM runs WHERE id IN ({placeholders})",
                    expired_run_ids,
                )
                connection.commit()
                deleted_run_count = len(expired_run_ids)
                deleted_event_count = expired_event_count

            return RetentionCleanupResult(
                retention_days=retention_days,
                cutoff=cutoff,
                dry_run=dry_run,
                expired_run_count=len(expired_run_ids),
                expired_event_count=expired_event_count,
                deleted_run_count=deleted_run_count,
                deleted_event_count=deleted_event_count,
                skipped_running_count=skipped_running_count,
                expired_run_ids=expired_run_ids,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _finish_run(self, run_id: str, status: RunStatus) -> AgentRun:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise RunNotFoundError(run_id)

            run = _row_to_run(row)
            if run.status != RunStatus.RUNNING:
                raise RunAlreadyEndedError(run_id)

            ended_at = now_utc()
            connection.execute(
                """
                UPDATE runs
                SET status = ?, ended_at = ?
                WHERE id = ?
                """,
                (status.value, ended_at.isoformat(), run_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        finished = self.get_run(run_id)
        if finished is None:
            raise RunNotFoundError(run_id)
        return finished

    def _count_events_for_run_ids(
        self,
        connection: sqlite3.Connection,
        run_ids: tuple[str, ...],
    ) -> int:
        if not run_ids:
            return 0
        placeholders = ",".join("?" for _ in run_ids)
        return connection.execute(
            f"SELECT COUNT(*) FROM run_events WHERE run_id IN ({placeholders})",
            run_ids,
        ).fetchone()[0]


def _to_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _from_json(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("stored JSON value must be an object")
    return parsed


def _row_to_run(row: sqlite3.Row) -> AgentRun:
    return AgentRun(
        id=row["id"],
        project_id=row["project_id"],
        session_id=row["session_id"],
        name=row["name"],
        status=RunStatus(row["status"]),
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        metadata=_from_json(row["metadata"]),
    )


def _row_to_run_list_item(row: sqlite3.Row) -> AgentRunListItem:
    run = _row_to_run(row)
    summary = RunDetailSummary(
        event_count=row["event_count"] or 0,
        message_count=row["message_count"] or 0,
        model_call_count=row["model_call_count"] or 0,
        tool_call_count=row["tool_call_count"] or 0,
        rag_retrieval_count=row["rag_retrieval_count"] or 0,
        evaluation_count=row["evaluation_count"] or 0,
        error_count=row["error_count"] or 0,
        total_tokens=row["total_tokens"] or 0,
        total_latency_ms=row["total_latency_ms"] or 0,
    )
    return AgentRunListItem(**run.model_dump(), summary=summary)


def _row_to_event(row: sqlite3.Row) -> RunEvent:
    return RunEvent(
        id=row["id"],
        run_id=row["run_id"],
        sequence=row["sequence"],
        type=row["type"],
        name=row["name"],
        timestamp=row["timestamp"],
        payload=_from_json(row["payload"]),
    )


def _row_to_audit_event(row: sqlite3.Row) -> AuditEvent:
    return AuditEvent(
        id=row["id"],
        project_id=row["project_id"],
        key_id=row["key_id"],
        scope=row["scope"],
        method=row["method"],
        path=row["path"],
        status_code=row["status_code"],
        outcome=AuditOutcome(row["outcome"]),
        reason=row["reason"],
        timestamp=row["timestamp"],
    )
