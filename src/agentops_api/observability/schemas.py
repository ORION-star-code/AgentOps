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


class RunDetailSummary(BaseModel):
    """Computed overview for a developer-facing run detail view."""

    event_count: int
    message_count: int
    model_call_count: int
    tool_call_count: int
    rag_retrieval_count: int
    evaluation_count: int
    error_count: int
    total_tokens: int
    total_latency_ms: int


class RunDetail(BaseModel):
    """Aggregated run detail contract for debugging one Agent execution."""

    run: AgentRun
    summary: RunDetailSummary
    timeline: list[RunEvent]
    messages: list[RunEvent]
    model_calls: list[RunEvent]
    tool_calls: list[RunEvent]
    rag_evidence: list[RunEvent]
    evaluations: list[RunEvent]
    errors: list[RunEvent]


def build_run_detail(run: AgentRun, events: list[RunEvent]) -> RunDetail:
    """Build an inspectable run detail payload from an ordered event timeline."""

    messages = _events_of_type(events, RunEventType.MESSAGE)
    model_calls = _events_of_type(events, RunEventType.MODEL_CALL)
    tool_calls = _events_of_type(events, RunEventType.TOOL_CALL)
    rag_evidence = _events_of_type(events, RunEventType.RAG_RETRIEVAL)
    evaluations = _events_of_type(events, RunEventType.EVALUATION)
    errors = _events_of_type(events, RunEventType.ERROR)
    summary = RunDetailSummary(
        event_count=len(events),
        message_count=len(messages),
        model_call_count=len(model_calls),
        tool_call_count=len(tool_calls),
        rag_retrieval_count=len(rag_evidence),
        evaluation_count=len(evaluations),
        error_count=len(errors),
        total_tokens=sum(_extract_int(event.payload, "token_count") for event in events),
        total_latency_ms=sum(_extract_int(event.payload, "latency_ms") for event in events),
    )

    return RunDetail(
        run=run,
        summary=summary,
        timeline=events,
        messages=messages,
        model_calls=model_calls,
        tool_calls=tool_calls,
        rag_evidence=rag_evidence,
        evaluations=evaluations,
        errors=errors,
    )


def _events_of_type(events: list[RunEvent], event_type: RunEventType) -> list[RunEvent]:
    return [event for event in events if event.type == event_type]


def _extract_int(payload: JsonObject, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, int):
        return value
    nested = payload.get("usage")
    if isinstance(nested, dict):
        nested_value = nested.get(key)
        if isinstance(nested_value, int):
            return nested_value
    return 0
