"""Trace storage configuration and repository factory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from agentops_api.audit import AuditEvent
from agentops_api.observability.repository import (
    DEFAULT_DB_PATH,
    RetentionCleanupResult,
    TraceRepository,
)
from agentops_api.observability.schemas import (
    AgentRun,
    AgentRunCreate,
    AgentRunListItem,
    RunDetailSummary,
    RunEvent,
    RunEventCreate,
    RunEventType,
    RunStatus,
)
from agentops_api.privacy import RetentionConfig

if TYPE_CHECKING:
    from agentops_api.evaluation import RegressionReport


class StorageBackend(StrEnum):
    """Supported trace storage backends."""

    SQLITE = "sqlite"
    POSTGRES = "postgres"


@dataclass(frozen=True)
class StorageConfig:
    """Runtime storage backend configuration."""

    backend: StorageBackend = StorageBackend.SQLITE
    sqlite_db_path: Path = DEFAULT_DB_PATH
    database_url: str | None = None


class PostgresStorageUnavailableError(RuntimeError):
    """Raised when PostgreSQL storage is requested before the adapter is implemented."""


@runtime_checkable
class TraceRepositoryProtocol(Protocol):
    """Repository contract that storage adapters must implement."""

    def create_run(self, payload: AgentRunCreate) -> AgentRun: ...

    def get_run(self, run_id: str) -> AgentRun | None: ...

    def list_runs(
        self,
        project_id: str,
        *,
        limit: int,
        status: RunStatus | None = None,
    ) -> list[AgentRun]: ...

    def list_runs_with_summaries(
        self,
        project_id: str,
        *,
        limit: int,
        status: RunStatus | None = None,
    ) -> list[AgentRunListItem]: ...

    def append_event(self, run_id: str, payload: RunEventCreate) -> RunEvent: ...

    def list_events(
        self,
        run_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
        event_type: RunEventType | None = None,
    ) -> list[RunEvent]: ...

    def list_recent_events(self, run_id: str, *, limit: int) -> list[RunEvent]: ...

    def get_event_summary(self, run_id: str) -> RunDetailSummary: ...

    def complete_run(self, run_id: str) -> AgentRun: ...

    def fail_run(self, run_id: str) -> AgentRun: ...

    def cancel_run(self, run_id: str) -> AgentRun: ...

    def save_regression_report(self, report: RegressionReport) -> RegressionReport: ...

    def get_regression_report(self, report_id: str) -> RegressionReport | None: ...

    def save_audit_event(self, event: AuditEvent) -> AuditEvent: ...

    def list_audit_events(
        self,
        *,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]: ...

    def cleanup_expired_runs(
        self,
        *,
        dry_run: bool = True,
        now: datetime | None = None,
    ) -> RetentionCleanupResult: ...


def load_storage_config(
    *,
    backend: str | None = None,
    sqlite_db_path: str | Path | None = None,
    database_url: str | None = None,
) -> StorageConfig:
    """Load storage configuration from environment-style values."""

    normalized_backend = (backend or StorageBackend.SQLITE.value).strip().lower()
    try:
        storage_backend = StorageBackend(normalized_backend)
    except ValueError as exc:
        allowed = ", ".join(backend.value for backend in StorageBackend)
        raise ValueError(f"AGENTOPS_STORAGE_BACKEND must be one of: {allowed}") from exc

    if storage_backend == StorageBackend.SQLITE:
        return StorageConfig(
            backend=storage_backend,
            sqlite_db_path=Path(sqlite_db_path) if sqlite_db_path is not None else DEFAULT_DB_PATH,
        )

    normalized_database_url = database_url.strip() if database_url is not None else None
    if not normalized_database_url:
        raise ValueError("AGENTOPS_DATABASE_URL is required when using postgres storage")
    return StorageConfig(
        backend=storage_backend,
        sqlite_db_path=Path(sqlite_db_path) if sqlite_db_path is not None else DEFAULT_DB_PATH,
        database_url=normalized_database_url,
    )


def create_trace_repository(
    config: StorageConfig,
    *,
    db_path: str | Path | None = None,
    retention_config: RetentionConfig | None = None,
) -> TraceRepositoryProtocol:
    """Create the configured trace repository implementation."""

    if config.backend == StorageBackend.SQLITE:
        return TraceRepository(
            db_path or config.sqlite_db_path,
            retention_config=retention_config,
        )

    raise PostgresStorageUnavailableError(
        "PostgreSQL trace storage is configured but the adapter is not implemented yet"
    )
