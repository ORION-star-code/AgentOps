"""API key authentication and project-scoped authorization."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from hmac import compare_digest
from typing import Any


class ApiScope(StrEnum):
    """Supported API key scopes."""

    INGEST = "ingest"
    READ = "read"
    EVALUATE = "evaluate"
    ADMIN = "admin"


@dataclass(frozen=True, init=False)
class ApiKeyCredential:
    """Configured API key bound to one project and a fixed scope set."""

    key: str
    project_id: str
    scopes: frozenset[ApiScope]

    def __init__(
        self,
        key: str,
        project_id: str,
        scopes: Iterable[ApiScope | str],
    ) -> None:
        normalized_key = key.strip()
        normalized_project_id = project_id.strip()
        normalized_scopes = frozenset(ApiScope(scope) for scope in scopes)

        if not normalized_key:
            raise ValueError("API key must not be empty")
        if not normalized_project_id:
            raise ValueError("API key project_id must not be empty")
        if not normalized_scopes:
            raise ValueError("API key must include at least one scope")

        object.__setattr__(self, "key", normalized_key)
        object.__setattr__(self, "project_id", normalized_project_id)
        object.__setattr__(self, "scopes", normalized_scopes)

    def allows(self, required_scope: ApiScope) -> bool:
        return ApiScope.ADMIN in self.scopes or required_scope in self.scopes


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Authenticated request context exposed to API handlers."""

    project_id: str
    scopes: frozenset[ApiScope]

    @classmethod
    def from_credential(cls, credential: ApiKeyCredential) -> AuthenticatedPrincipal:
        return cls(project_id=credential.project_id, scopes=credential.scopes)

    def allows(self, required_scope: ApiScope) -> bool:
        return ApiScope.ADMIN in self.scopes or required_scope in self.scopes


class ApiKeyStore:
    """In-memory API key lookup table."""

    def __init__(self, credentials: Iterable[ApiKeyCredential] = ()) -> None:
        self._credentials = tuple(credentials)

    def authenticate(self, api_key: str) -> AuthenticatedPrincipal | None:
        for credential in self._credentials:
            if compare_digest(credential.key, api_key):
                return AuthenticatedPrincipal.from_credential(credential)
        return None


def load_api_key_credentials(raw_config: str | None) -> list[ApiKeyCredential]:
    """Load credentials from a JSON environment variable value."""

    if raw_config is None or not raw_config.strip():
        return []

    parsed = json.loads(raw_config)
    if not isinstance(parsed, list):
        raise ValueError("AGENTOPS_API_KEYS must be a JSON array")

    return [_credential_from_mapping(item) for item in parsed]


def _credential_from_mapping(item: Any) -> ApiKeyCredential:
    if not isinstance(item, Mapping):
        raise ValueError("each API key entry must be a JSON object")

    key = item.get("key")
    project_id = item.get("project_id")
    scopes = item.get("scopes")
    if not isinstance(key, str):
        raise ValueError("API key entry requires string key")
    if not isinstance(project_id, str):
        raise ValueError("API key entry requires string project_id")
    if not isinstance(scopes, list):
        raise ValueError("API key entry requires list scopes")
    if not all(isinstance(scope, str) for scope in scopes):
        raise ValueError("API key scopes must be strings")

    return ApiKeyCredential(key=key, project_id=project_id, scopes=scopes)
