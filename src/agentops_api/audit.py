"""Security audit event contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditOutcome(StrEnum):
    """Outcome categories for audited API operations."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AuditEvent(BaseModel):
    """Non-sensitive audit record for a security-relevant API request."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str | None = None
    key_id: str | None = None
    scope: str | None = None
    method: str
    path: str
    status_code: int = Field(ge=100, le=599)
    outcome: AuditOutcome
    reason: str | None = Field(default=None, max_length=200)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
