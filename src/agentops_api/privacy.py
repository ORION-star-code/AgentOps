"""Sensitive trace redaction and retention configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agentops_api.observability.schemas import JsonObject

REDACTED_VALUE = "[REDACTED]"
REDACTION_EVIDENCE_KEY = "_agentops_redaction"

_SENSITIVE_EXACT_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}


@dataclass(frozen=True)
class RedactionResult:
    """Redacted JSON object plus field-level evidence."""

    value: JsonObject
    redacted_fields: tuple[str, ...]

    @property
    def redaction_count(self) -> int:
        return len(self.redacted_fields)


@dataclass(frozen=True)
class RetentionConfig:
    """Trace retention settings.

    ``days=None`` means local data is retained indefinitely.
    """

    days: int | None = None

    @property
    def enabled(self) -> bool:
        return self.days is not None


def load_retention_config(raw_days: str | None) -> RetentionConfig:
    """Load retention configuration from ``AGENTOPS_RETENTION_DAYS``."""

    if raw_days is None or not raw_days.strip():
        return RetentionConfig()

    try:
        days = int(raw_days)
    except ValueError as exc:
        raise ValueError("AGENTOPS_RETENTION_DAYS must be a positive integer") from exc

    if days < 1:
        raise ValueError("AGENTOPS_RETENTION_DAYS must be a positive integer")
    return RetentionConfig(days=days)


def redact_json_object(value: JsonObject, *, path_prefix: str) -> RedactionResult:
    """Redact sensitive keys recursively and add redaction evidence when needed."""

    redacted_fields: list[str] = []
    redacted_value = _redact_value(value, path_prefix, redacted_fields)
    if not isinstance(redacted_value, dict):
        raise ValueError("redacted JSON value must remain an object")

    if redacted_fields:
        redacted_value[REDACTION_EVIDENCE_KEY] = {
            "redaction_count": len(redacted_fields),
            "redacted_fields": redacted_fields,
        }

    return RedactionResult(value=redacted_value, redacted_fields=tuple(redacted_fields))


def _redact_value(value: Any, path: str, redacted_fields: list[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact_mapping_value(key, nested_value, f"{path}.{key}", redacted_fields)
            for key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [
            _redact_value(nested_value, f"{path}[{index}]", redacted_fields)
            for index, nested_value in enumerate(value)
        ]
    return value


def _redact_mapping_value(
    key: str,
    value: Any,
    path: str,
    redacted_fields: list[str],
) -> Any:
    if _is_sensitive_key(key):
        redacted_fields.append(path)
        return REDACTED_VALUE
    return _redact_value(value, path, redacted_fields)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    compact = re.sub(r"[\s_-]+", "", normalized)
    if normalized in _SENSITIVE_EXACT_KEYS or compact in _SENSITIVE_EXACT_KEYS:
        return True

    if normalized.endswith(("_api_key", "-api-key", ".api_key", ".api-key")):
        return True
    if normalized.endswith(("_token", "-token", ".token")):
        return True
    if normalized.endswith(("_password", "-password", ".password")):
        return True
    if normalized.endswith(("_secret", "-secret", ".secret")):
        return True
    if normalized.startswith(("password_", "password-", "secret_", "secret-")):
        return True

    return False
