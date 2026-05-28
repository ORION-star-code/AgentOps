"""SQLite-backed trace event repository."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentops_api.observability.schemas import (
    AgentRun,
    AgentRunCreate,
    RunEvent,
    RunEventCreate,
    RunStatus,
    now_utc,
)
from agentops_api.privacy import RetentionConfig, redact_json_object

DEFAULT_DB_PATH = Path(".agentops") / "agentops.db"


class RunNotFoundError(LookupError):
    """Raised when a run-scoped operation targets an unknown run."""


class RunAlreadyEndedError(RuntimeError):
    """Raised when a write targets a run that has already ended."""


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

    def list_events(self, run_id: str) -> list[RunEvent]:
        if self.get_run(run_id) is None:
            raise RunNotFoundError(run_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM run_events WHERE run_id = ? ORDER BY sequence ASC",
                (run_id,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def complete_run(self, run_id: str) -> AgentRun:
        return self._finish_run(run_id, RunStatus.SUCCEEDED)

    def fail_run(self, run_id: str) -> AgentRun:
        return self._finish_run(run_id, RunStatus.FAILED)

    def cancel_run(self, run_id: str) -> AgentRun:
        return self._finish_run(run_id, RunStatus.CANCELED)

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
