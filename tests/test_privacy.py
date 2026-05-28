import pytest

from agentops_api.privacy import REDACTED_VALUE, load_retention_config, redact_json_object


def test_redact_json_object_redacts_sensitive_keys_recursively() -> None:
    result = redact_json_object(
        {
            "api_key": "sk-secret",
            "nested": {
                "authorization": "Bearer token",
                "items": [{"client_secret": "hidden"}],
            },
        },
        path_prefix="payload",
    )

    assert result.value["api_key"] == REDACTED_VALUE
    assert result.value["nested"]["authorization"] == REDACTED_VALUE
    assert result.value["nested"]["items"][0]["client_secret"] == REDACTED_VALUE
    assert result.value["_agentops_redaction"] == {
        "redaction_count": 3,
        "redacted_fields": [
            "payload.api_key",
            "payload.nested.authorization",
            "payload.nested.items[0].client_secret",
        ],
    }


def test_redact_json_object_does_not_redact_token_count() -> None:
    result = redact_json_object(
        {"token_count": 42, "latency_ms": 128},
        path_prefix="payload",
    )

    assert result.value == {"token_count": 42, "latency_ms": 128}
    assert result.redaction_count == 0


def test_load_retention_config_defaults_to_indefinite() -> None:
    config = load_retention_config(None)

    assert config.days is None
    assert config.enabled is False


def test_load_retention_config_accepts_positive_days() -> None:
    config = load_retention_config("30")

    assert config.days == 30
    assert config.enabled is True


@pytest.mark.parametrize("raw_days", ["0", "-1", "soon"])
def test_load_retention_config_rejects_invalid_values(raw_days: str) -> None:
    with pytest.raises(ValueError, match="AGENTOPS_RETENTION_DAYS"):
        load_retention_config(raw_days)
