"""Trace schemas for Agent run observability."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_JSON_BYTES = 64 * 1024

JsonObject = dict[str, Any]


class RunStatus(StrEnum):
    """Lifecycle status for one Agent run."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class RunEventType(StrEnum):
    """Supported timeline event types."""

    MESSAGE = "message"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    RAG_RETRIEVAL = "rag_retrieval"
    ERROR = "error"
    EVALUATION = "evaluation"
    CUSTOM = "custom"


def now_utc() -> datetime:
    return datetime.now(UTC)


def validate_json_size(value: JsonObject) -> JsonObject:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise ValueError(f"JSON object must be at most {MAX_JSON_BYTES} bytes")
    return value


class AgentRunCreate(BaseModel):
    """Client payload for creating an Agent run."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, max_length=500)
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_fit(cls, value: JsonObject) -> JsonObject:
        return validate_json_size(value)


class AgentRun(BaseModel):
    """Persisted Agent run summary."""

    id: str
    project_id: str
    session_id: str | None
    name: str | None
    status: RunStatus
    started_at: datetime
    ended_at: datetime | None
    metadata: JsonObject


class RunEventCreate(BaseModel):
    """Client payload for appending one timeline event."""

    model_config = ConfigDict(extra="forbid")

    type: RunEventType
    name: str | None = Field(default=None, max_length=500)
    payload: JsonObject = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def payload_must_fit(cls, value: JsonObject) -> JsonObject:
        return validate_json_size(value)


class RunEvent(BaseModel):
    """Persisted append-only event in an Agent run timeline."""

    id: str
    run_id: str
    sequence: int
    type: RunEventType
    name: str | None
    timestamp: datetime
    payload: JsonObject
