import json

import httpx
import pytest

from agentops_api.evaluation import (
    DEFAULT_MIMO_BASE_URL,
    DEFAULT_MIMO_MODEL,
    EvaluationJudgeCreate,
    MimoJudgeAPIError,
    MimoJudgeConfig,
    MimoJudgeNotConfiguredError,
    MimoJudgeProvider,
    MimoJudgeResponseError,
    MimoJudgeTimeoutError,
    load_mimo_judge_config,
)


def _openai_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


def _judge_payload() -> EvaluationJudgeCreate:
    return EvaluationJudgeCreate(
        question="Who does the policy apply to?",
        answer="The policy applies to enterprise users.",
        context=["The policy applies to enterprise users."],
        metrics=["groundedness", "hallucination_risk"],
        rubric_id="enterprise-policy",
        rubric_version="v1",
        threshold_profile="strict",
        metadata={"dataset_id": "smoke"},
    )


def test_mimo_provider_builds_openai_compatible_request_and_parses_metrics() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return _openai_response(
            json.dumps(
                {
                    "metrics": [
                        {
                            "name": "groundedness",
                            "score": 0.86,
                            "rationale": "The answer is supported by the supplied context.",
                        },
                        {
                            "name": "hallucination_risk",
                            "score": 0.12,
                            "rationale": "No unsupported claims were introduced.",
                        },
                    ]
                }
            )
        )

    provider = MimoJudgeProvider(
        MimoJudgeConfig(api_key="test-mimo-key", max_retries=0),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.evaluate(_judge_payload())

    assert captured["url"] == f"{DEFAULT_MIMO_BASE_URL}/chat/completions"
    assert captured["authorization"] == "Bearer test-mimo-key"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == DEFAULT_MIMO_MODEL
    assert body["response_format"] == {"type": "json_object"}
    assert result.evaluator_id == "mimo-llm-judge"
    assert result.evaluator_version == "0.1.0"
    assert result.judge_model == DEFAULT_MIMO_MODEL
    assert result.rubric_id == "enterprise-policy"
    assert result.rubric_version == "v1"
    assert result.threshold_profile == "strict"
    assert [metric.name for metric in result.metrics] == [
        "groundedness",
        "hallucination_risk",
    ]


def test_mimo_provider_requires_api_key() -> None:
    provider = MimoJudgeProvider(MimoJudgeConfig(api_key=None))

    with pytest.raises(MimoJudgeNotConfiguredError):
        provider.evaluate(_judge_payload())


def test_mimo_provider_rejects_invalid_json_content() -> None:
    provider = MimoJudgeProvider(
        MimoJudgeConfig(api_key="test-mimo-key", max_retries=0),
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: _openai_response("nope"))),
    )

    with pytest.raises(MimoJudgeResponseError):
        provider.evaluate(_judge_payload())


def test_mimo_provider_rejects_missing_metric() -> None:
    provider = MimoJudgeProvider(
        MimoJudgeConfig(api_key="test-mimo-key", max_retries=0),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: _openai_response(
                    json.dumps(
                        {
                            "metrics": [
                                {
                                    "name": "groundedness",
                                    "score": 0.86,
                                    "rationale": "Grounded.",
                                }
                            ]
                        }
                    )
                )
            )
        ),
    )

    with pytest.raises(MimoJudgeResponseError, match="missing metrics"):
        provider.evaluate(_judge_payload())


def test_mimo_provider_rejects_invalid_metric_score() -> None:
    provider = MimoJudgeProvider(
        MimoJudgeConfig(api_key="test-mimo-key", max_retries=0),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: _openai_response(
                    json.dumps(
                        {
                            "metrics": [
                                {"name": "groundedness", "score": 1.2},
                                {"name": "hallucination_risk", "score": 0.1},
                            ]
                        }
                    )
                )
            )
        ),
    )

    with pytest.raises(MimoJudgeResponseError, match="invalid metric"):
        provider.evaluate(_judge_payload())


def test_mimo_provider_maps_timeout() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow judge")

    provider = MimoJudgeProvider(
        MimoJudgeConfig(api_key="test-mimo-key", max_retries=0),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(MimoJudgeTimeoutError):
        provider.evaluate(_judge_payload())


def test_mimo_provider_maps_api_error() -> None:
    provider = MimoJudgeProvider(
        MimoJudgeConfig(api_key="test-mimo-key", max_retries=0),
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(500))),
    )

    with pytest.raises(MimoJudgeAPIError):
        provider.evaluate(_judge_payload())


def test_load_mimo_config_uses_safe_defaults_and_env_overrides() -> None:
    config = load_mimo_judge_config(
        {
            "AGENTOPS_MIMO_API_KEY": "test-mimo-key",
            "AGENTOPS_MIMO_BASE_URL": "https://example.test/v1",
            "AGENTOPS_MIMO_MODEL": "mimo-test",
            "AGENTOPS_MIMO_TIMEOUT_SECONDS": "9.5",
            "AGENTOPS_MIMO_MAX_RETRIES": "2",
        }
    )

    assert config.is_configured is True
    assert config.chat_completions_url == "https://example.test/v1/chat/completions"
    assert config.model == "mimo-test"
    assert config.timeout_seconds == 9.5
    assert config.max_retries == 2
