"""Xiaomi Mimo LLM-as-judge provider."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import ValidationError

from agentops_api.evaluation.schemas import (
    EvaluationJudgeCreate,
    EvaluationMetricInput,
    EvaluationMetricName,
    EvaluationResultCreate,
)

DEFAULT_MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_MIMO_MODEL = "mimo-v2.5-pro"
MIMO_EVALUATOR_ID = "mimo-llm-judge"
MIMO_EVALUATOR_VERSION = "0.1.0"
DEFAULT_MIMO_TIMEOUT_SECONDS = 30.0
DEFAULT_MIMO_MAX_RETRIES = 1


class MimoJudgeError(RuntimeError):
    """Base class for Mimo judge provider failures."""


class MimoJudgeNotConfiguredError(MimoJudgeError):
    """Raised when the Mimo API key is not configured."""


class MimoJudgeTimeoutError(MimoJudgeError):
    """Raised when the Mimo judge request times out."""


class MimoJudgeAPIError(MimoJudgeError):
    """Raised when the Mimo API returns or triggers a transport failure."""


class MimoJudgeResponseError(MimoJudgeError):
    """Raised when the judge response cannot be converted into evaluation metrics."""


@dataclass(frozen=True)
class MimoJudgeConfig:
    """Configuration for the OpenAI-compatible Mimo judge API."""

    api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_MIMO_BASE_URL
    model: str = DEFAULT_MIMO_MODEL
    timeout_seconds: float = DEFAULT_MIMO_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MIMO_MAX_RETRIES

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def load_mimo_judge_config(env: Mapping[str, str] | None = None) -> MimoJudgeConfig:
    """Load Mimo judge settings from environment variables."""

    source = os.environ if env is None else env
    timeout_seconds = _parse_positive_float(
        source.get("AGENTOPS_MIMO_TIMEOUT_SECONDS"),
        default=DEFAULT_MIMO_TIMEOUT_SECONDS,
        name="AGENTOPS_MIMO_TIMEOUT_SECONDS",
    )
    max_retries = _parse_non_negative_int(
        source.get("AGENTOPS_MIMO_MAX_RETRIES"),
        default=DEFAULT_MIMO_MAX_RETRIES,
        name="AGENTOPS_MIMO_MAX_RETRIES",
    )
    return MimoJudgeConfig(
        api_key=source.get("AGENTOPS_MIMO_API_KEY"),
        base_url=source.get("AGENTOPS_MIMO_BASE_URL", DEFAULT_MIMO_BASE_URL),
        model=source.get("AGENTOPS_MIMO_MODEL", DEFAULT_MIMO_MODEL),
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


class MimoJudgeProvider:
    """Generate deterministic evaluation payloads through Xiaomi Mimo."""

    def __init__(
        self,
        config: MimoJudgeConfig | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config or load_mimo_judge_config()
        self._client = client or httpx.Client()

    def evaluate(self, payload: EvaluationJudgeCreate) -> EvaluationResultCreate:
        if not self.config.is_configured:
            raise MimoJudgeNotConfiguredError("Mimo judge API key is not configured")

        response_json = self._request_judgement(payload)
        metrics = _parse_metric_response(response_json, payload.metrics)
        return EvaluationResultCreate(
            answer=payload.answer,
            evaluator_name=MIMO_EVALUATOR_ID,
            evaluator_id=MIMO_EVALUATOR_ID,
            evaluator_version=MIMO_EVALUATOR_VERSION,
            rubric_id=payload.rubric_id,
            rubric_version=payload.rubric_version,
            judge_model=self.config.model,
            threshold_profile=payload.threshold_profile,
            rag_event_id=payload.rag_event_id,
            metrics=metrics,
            metadata=payload.metadata,
        )

    def _request_judgement(self, payload: EvaluationJudgeCreate) -> dict[str, Any]:
        request_body = _build_chat_completion_request(self.config.model, payload)
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        last_timeout: httpx.TimeoutException | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._client.post(
                    self.config.chat_completions_url,
                    headers=headers,
                    json=request_body,
                    timeout=self.config.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                last_timeout = exc
                if attempt < self.config.max_retries:
                    continue
                raise MimoJudgeTimeoutError("Mimo judge request timed out") from exc
            except httpx.HTTPError as exc:
                raise MimoJudgeAPIError("Mimo judge API request failed") from exc

            if response.status_code >= 500 and attempt < self.config.max_retries:
                continue
            if response.status_code >= 400:
                raise MimoJudgeAPIError(
                    f"Mimo judge API returned HTTP {response.status_code}",
                )
            try:
                return response.json()
            except ValueError as exc:
                raise MimoJudgeResponseError("Mimo judge API returned invalid JSON") from exc

        raise MimoJudgeTimeoutError("Mimo judge request timed out") from last_timeout


def _build_chat_completion_request(model: str, payload: EvaluationJudgeCreate) -> dict[str, Any]:
    requested_metrics = [metric.value for metric in payload.metrics]
    user_payload = {
        "question": payload.question,
        "answer": payload.answer,
        "context": payload.context,
        "rubric_id": payload.rubric_id,
        "rubric_version": payload.rubric_version,
        "threshold_profile": payload.threshold_profile,
        "metrics": requested_metrics,
    }
    return {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an LLM-as-judge for an Agent observability platform. "
                    "Return only valid JSON. Evaluate each requested metric with a score "
                    "between 0 and 1 plus a concise rationale. The JSON shape must be "
                    '{"metrics":[{"name":"groundedness","score":0.0,"rationale":"..."}]}.'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
            },
        ],
    }


def _parse_metric_response(
    response_json: dict[str, Any],
    requested_metrics: list[EvaluationMetricName],
) -> list[EvaluationMetricInput]:
    content = _extract_message_content(response_json)
    try:
        parsed_content = json.loads(content)
    except ValueError as exc:
        raise MimoJudgeResponseError("Mimo judge response content was not valid JSON") from exc
    if not isinstance(parsed_content, dict):
        raise MimoJudgeResponseError("Mimo judge response must be a JSON object")

    raw_metrics = parsed_content.get("metrics")
    if not isinstance(raw_metrics, list):
        raise MimoJudgeResponseError("Mimo judge response requires a metrics list")

    parsed_by_name: dict[EvaluationMetricName, EvaluationMetricInput] = {}
    for raw_metric in raw_metrics:
        try:
            metric = EvaluationMetricInput.model_validate(raw_metric)
        except ValidationError as exc:
            raise MimoJudgeResponseError("Mimo judge returned an invalid metric") from exc
        if metric.name in parsed_by_name:
            raise MimoJudgeResponseError("Mimo judge returned duplicate metrics")
        parsed_by_name[metric.name] = metric

    missing = [metric.value for metric in requested_metrics if metric not in parsed_by_name]
    if missing:
        raise MimoJudgeResponseError(f"Mimo judge response missing metrics: {', '.join(missing)}")

    return [parsed_by_name[metric] for metric in requested_metrics]


def _extract_message_content(response_json: dict[str, Any]) -> str:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MimoJudgeResponseError("Mimo judge response missing message content") from exc
    if not isinstance(content, str) or not content.strip():
        raise MimoJudgeResponseError("Mimo judge response content must be a non-empty string")
    return content


def _parse_positive_float(raw_value: str | None, *, default: float, name: str) -> float:
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive number")
    return parsed


def _parse_non_negative_int(raw_value: str | None, *, default: int, name: str) -> int:
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return parsed
