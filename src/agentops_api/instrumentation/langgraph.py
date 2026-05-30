"""Lightweight LangGraph instrumentation helpers."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import Any, ParamSpec, Protocol, TypeVar

from agentops_api.sdk import JsonObject

P = ParamSpec("P")
R = TypeVar("R")


class _AgentOpsClient(Protocol):
    project_id: str

    def create_run(
        self,
        *,
        session_id: str | None = None,
        name: str | None = None,
        metadata: JsonObject | None = None,
        project_id: str | None = None,
    ) -> JsonObject:
        """Create an AgentOps run."""

    def append_event(
        self,
        run_id: str,
        event_type: str,
        *,
        name: str | None = None,
        payload: JsonObject | None = None,
    ) -> JsonObject:
        """Append one timeline event."""

    def complete_run(self, run_id: str) -> JsonObject:
        """Mark a run as succeeded."""

    def fail_run(self, run_id: str) -> JsonObject:
        """Mark a run as failed."""


Clock = Callable[[], float]


class LangGraphInstrumentation:
    """Factory for tracing LangGraph-like execution through AgentOpsClient."""

    def __init__(
        self,
        client: _AgentOpsClient,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.client = client
        self._clock = clock or _perf_counter

    def trace_run(
        self,
        *,
        name: str = "LangGraph run",
        session_id: str | None = None,
        metadata: JsonObject | None = None,
    ) -> _LangGraphRunContext:
        """Create a context manager that opens and closes an AgentOps run."""

        return _LangGraphRunContext(
            instrumentation=self,
            name=name,
            session_id=session_id,
            metadata=metadata or {},
        )

    def attach_run(self, run_id: str) -> LangGraphRun:
        """Attach instrumentation helpers to an existing AgentOps run."""

        return LangGraphRun(run_id=run_id, client=self.client, clock=self._clock)


@dataclass
class LangGraphRun:
    """Convenience recorder for one LangGraph execution run."""

    run_id: str
    client: _AgentOpsClient
    clock: Clock

    _has_error_event: bool = False

    def record_message(
        self,
        role: str,
        content: str,
        *,
        metadata: JsonObject | None = None,
    ) -> JsonObject:
        return self.client.append_event(
            self.run_id,
            "message",
            name="langgraph_message",
            payload={
                "instrumentation": "langgraph",
                "role": role,
                "content": content,
                "metadata": metadata or {},
            },
        )

    def record_model_call(
        self,
        *,
        model_name: str,
        prompt: str | None = None,
        response: str | None = None,
        token_count: int | None = None,
        latency_ms: int | None = None,
        metadata: JsonObject | None = None,
    ) -> JsonObject:
        return self.client.append_event(
            self.run_id,
            "model_call",
            name="langgraph_model_call",
            payload={
                "instrumentation": "langgraph",
                "model_name": model_name,
                "prompt": prompt,
                "response": response,
                "usage": _usage_payload(token_count=token_count, latency_ms=latency_ms),
                "metadata": metadata or {},
            },
        )

    def record_tool_call(
        self,
        *,
        tool_name: str,
        arguments: JsonObject | None = None,
        result: Any | None = None,
        token_count: int | None = None,
        latency_ms: int | None = None,
        metadata: JsonObject | None = None,
    ) -> JsonObject:
        return self.client.append_event(
            self.run_id,
            "tool_call",
            name="langgraph_tool_call",
            payload={
                "instrumentation": "langgraph",
                "tool_name": tool_name,
                "arguments": arguments or {},
                "result": result,
                "usage": _usage_payload(token_count=token_count, latency_ms=latency_ms),
                "metadata": metadata or {},
            },
        )

    def record_error(
        self,
        error: BaseException,
        *,
        node_name: str | None = None,
        metadata: JsonObject | None = None,
    ) -> JsonObject:
        self._has_error_event = True
        return self.client.append_event(
            self.run_id,
            "error",
            name="langgraph_error",
            payload={
                "instrumentation": "langgraph",
                "node_name": node_name,
                "error_type": type(error).__name__,
                "message": str(error),
                "metadata": metadata or {},
            },
        )

    def record_custom(
        self,
        name: str,
        payload: JsonObject | None = None,
    ) -> JsonObject:
        custom_payload = {"instrumentation": "langgraph"}
        custom_payload.update(payload or {})
        return self.client.append_event(
            self.run_id,
            "custom",
            name=name,
            payload=custom_payload,
        )

    def node(
        self,
        node_name: str,
        *,
        metadata: JsonObject | None = None,
    ) -> _LangGraphNodeContext:
        return _LangGraphNodeContext(self, node_name=node_name, metadata=metadata or {})

    def wrap_node(
        self,
        node_name: str,
        func: Callable[P, R],
        *,
        metadata: JsonObject | None = None,
    ) -> Callable[P, R]:
        """Wrap a LangGraph node function and emit one node event around it."""

        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            with self.node(node_name, metadata=metadata):
                return func(*args, **kwargs)

        return wrapped


class _LangGraphRunContext(AbstractContextManager[LangGraphRun]):
    def __init__(
        self,
        *,
        instrumentation: LangGraphInstrumentation,
        name: str,
        session_id: str | None,
        metadata: JsonObject,
    ) -> None:
        self._instrumentation = instrumentation
        self._name = name
        self._session_id = session_id
        self._metadata = metadata
        self.run: LangGraphRun | None = None

    def __enter__(self) -> LangGraphRun:
        created = self._instrumentation.client.create_run(
            session_id=self._session_id,
            name=self._name,
            metadata={
                "agent_framework": "langgraph",
                "instrumentation": "agentops-python",
                **self._metadata,
            },
        )
        self.run = self._instrumentation.attach_run(str(created["id"]))
        return self.run

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.run is None:
            return
        if exc is None:
            self.run.client.complete_run(self.run.run_id)
            return
        if not self.run._has_error_event:
            self.run.record_error(exc)
        self.run.client.fail_run(self.run.run_id)


class _LangGraphNodeContext(AbstractContextManager[None]):
    def __init__(
        self,
        run: LangGraphRun,
        *,
        node_name: str,
        metadata: JsonObject,
    ) -> None:
        self._run = run
        self._node_name = node_name
        self._metadata = metadata
        self._started_at = 0.0

    def __enter__(self) -> None:
        self._started_at = self._run.clock()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        latency_ms = _elapsed_ms(self._started_at, self._run.clock())
        status = "succeeded" if exc is None else "failed"
        self._run.record_custom(
            "langgraph_node",
            {
                "event": "node",
                "node_name": self._node_name,
                "status": status,
                "latency_ms": latency_ms,
                "metadata": self._metadata,
            },
        )
        if exc is not None:
            self._run.record_error(exc, node_name=self._node_name, metadata=self._metadata)


def _usage_payload(
    *,
    token_count: int | None,
    latency_ms: int | None,
) -> JsonObject:
    usage: JsonObject = {}
    if token_count is not None:
        usage["token_count"] = token_count
    if latency_ms is not None:
        usage["latency_ms"] = latency_ms
    return usage


def _elapsed_ms(start: float, end: float) -> int:
    return max(0, int(round((end - start) * 1000)))


def _perf_counter() -> float:
    from time import perf_counter

    return perf_counter()
