"""Python ingestion SDK for AgentOps."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol, Self

import httpx

JsonObject = dict[str, Any]
JsonValue = JsonObject | list[Any]

API_KEY_HEADER = "X-AgentOps-API-Key"


class AgentOpsClientError(RuntimeError):
    """Base SDK error."""


class AgentOpsAPIError(AgentOpsClientError):
    """Raised when the AgentOps API returns a non-2xx response."""

    def __init__(
        self,
        status_code: int,
        detail: Any,
        *,
        response: httpx.Response | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.response = response
        super().__init__(f"AgentOps API returned {status_code}: {detail}")


class _HTTPClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send an HTTP request."""


class AgentOpsClient:
    """Small synchronous client for writing AgentOps trace and evaluation evidence."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8000",
        api_key: str,
        project_id: str,
        timeout_seconds: float = 30.0,
        http_client: _HTTPClient | None = None,
    ) -> None:
        self.project_id = project_id
        self._api_key = api_key
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client and hasattr(self._client, "close"):
            self._client.close()

    def health(self) -> JsonObject:
        return self._request("GET", "/health")

    def create_run(
        self,
        *,
        session_id: str | None = None,
        name: str | None = None,
        metadata: JsonObject | None = None,
        project_id: str | None = None,
    ) -> JsonObject:
        return self._request(
            "POST",
            "/v1/runs",
            json={
                "project_id": project_id or self.project_id,
                "session_id": session_id,
                "name": name,
                "metadata": metadata or {},
            },
        )

    def get_run(self, run_id: str) -> JsonObject:
        return self._request("GET", f"/v1/runs/{run_id}")

    def get_run_detail(self, run_id: str) -> JsonObject:
        return self._request("GET", f"/v1/runs/{run_id}/detail")

    def append_event(
        self,
        run_id: str,
        event_type: str,
        *,
        name: str | None = None,
        payload: JsonObject | None = None,
    ) -> JsonObject:
        return self._request(
            "POST",
            f"/v1/runs/{run_id}/events",
            json={
                "type": event_type,
                "name": name,
                "payload": payload or {},
            },
        )

    def list_events(
        self,
        run_id: str,
        *,
        limit: int = 100,
        after_sequence: int | None = None,
        event_type: str | None = None,
    ) -> list[JsonObject]:
        params: dict[str, Any] = {"limit": limit}
        if after_sequence is not None:
            params["after_sequence"] = after_sequence
        if event_type is not None:
            params["type"] = event_type
        return self._request("GET", f"/v1/runs/{run_id}/events", params=params)

    def append_rag_evidence(self, run_id: str, evidence: JsonObject) -> JsonObject:
        return self._request(
            "POST",
            f"/v1/runs/{run_id}/rag/evidence",
            json=evidence,
        )

    def append_evaluation(self, run_id: str, evaluation: JsonObject) -> JsonObject:
        return self._request(
            "POST",
            f"/v1/runs/{run_id}/evaluations",
            json=evaluation,
        )

    def judge_evaluation(self, run_id: str, payload: JsonObject) -> JsonObject:
        return self._request(
            "POST",
            f"/v1/runs/{run_id}/evaluations/judge",
            json=payload,
        )

    def complete_run(self, run_id: str) -> JsonObject:
        return self._request("POST", f"/v1/runs/{run_id}/complete")

    def fail_run(self, run_id: str) -> JsonObject:
        return self._request("POST", f"/v1/runs/{run_id}/fail")

    def cancel_run(self, run_id: str) -> JsonObject:
        return self._request("POST", f"/v1/runs/{run_id}/cancel")

    def run_golden_dataset(
        self,
        dataset: JsonObject,
        *,
        judge_mode: str = "deterministic",
        rubric_id: str | None = None,
        rubric_version: str | None = None,
        threshold_profile: str | None = None,
        metrics: list[str] | None = None,
        metadata: JsonObject | None = None,
        project_id: str | None = None,
    ) -> JsonObject:
        payload: JsonObject = {
            "project_id": project_id or self.project_id,
            "dataset": dataset,
            "judge_mode": judge_mode,
            "metadata": metadata or {},
        }
        if rubric_id is not None:
            payload["rubric_id"] = rubric_id
        if rubric_version is not None:
            payload["rubric_version"] = rubric_version
        if threshold_profile is not None:
            payload["threshold_profile"] = threshold_profile
        if metrics is not None:
            payload["metrics"] = metrics
        return self._request("POST", "/v1/golden-datasets/runs", json=payload)

    def compare_golden_dataset_runs(
        self,
        *,
        baseline_run_id: str,
        candidate_run_id: str,
        baseline_version: str,
        candidate_version: str,
        baseline_prompt_version: str | None = None,
        candidate_prompt_version: str | None = None,
        baseline_model_version: str | None = None,
        candidate_model_version: str | None = None,
        regression_tolerance: float = 0.05,
        metadata: JsonObject | None = None,
        project_id: str | None = None,
    ) -> JsonObject:
        return self._request(
            "POST",
            "/v1/golden-datasets/regressions/compare",
            json={
                "project_id": project_id or self.project_id,
                "baseline_run_id": baseline_run_id,
                "candidate_run_id": candidate_run_id,
                "baseline_version": baseline_version,
                "candidate_version": candidate_version,
                "baseline_prompt_version": baseline_prompt_version,
                "candidate_prompt_version": candidate_prompt_version,
                "baseline_model_version": baseline_model_version,
                "candidate_model_version": candidate_model_version,
                "regression_tolerance": regression_tolerance,
                "metadata": metadata or {},
            },
        )

    def compare_regression(self, payload: JsonObject) -> JsonObject:
        return self._request("POST", "/v1/regressions/compare", json=payload)

    def get_regression_report(self, report_id: str) -> JsonObject:
        return self._request("GET", f"/v1/regressions/reports/{report_id}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: JsonValue | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = self._client.request(
            method,
            path,
            json=json,
            params=params,
            headers={API_KEY_HEADER: self._api_key},
        )
        response_json = _parse_response_json(response)
        if response.status_code >= 400:
            detail = response_json.get("detail") if isinstance(response_json, dict) else response.text
            raise AgentOpsAPIError(response.status_code, detail, response=response)
        return response_json


def _parse_response_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        if response.status_code >= 400:
            return {"detail": response.text}
        raise AgentOpsClientError("AgentOps API returned invalid JSON") from exc
