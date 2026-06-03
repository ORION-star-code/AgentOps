"""API key authentication and project-scoped authorization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from hmac import compare_digest
import json
from typing import Any


API_KEY_HASH_PREFIX = "sha256:"
API_KEY_HASH_LENGTH = 64


class ApiScope(StrEnum):
    """Supported API key scopes."""

    INGEST = "ingest"
    READ = "read"
    EVALUATE = "evaluate"
    ADMIN = "admin"


@dataclass(frozen=True, init=False)
class ApiKeyCredential:
    """Configured API key bound to one project and a fixed scope set."""

    key_hash: str
    project_id: str
    scopes: frozenset[ApiScope]
    key_id: str | None
    revoked: bool

    def __init__(
        self,
        project_id: str,
        scopes: Iterable[ApiScope | str],
        *,
        key: str | None = None,
        key_hash: str | None = None,
        key_id: str | None = None,
        revoked: bool = False,
    ) -> None:
        normalized_hash = _credential_hash_from_secret_or_hash(key=key, key_hash=key_hash)
        normalized_project_id = project_id.strip()
        normalized_scopes = frozenset(ApiScope(scope) for scope in scopes)
        normalized_key_id = key_id.strip() if key_id is not None else None

        if not normalized_project_id:
            raise ValueError("API key project_id must not be empty")
        if not normalized_scopes:
            raise ValueError("API key must include at least one scope")
        if normalized_key_id == "":
            raise ValueError("API key key_id must not be empty")

        object.__setattr__(self, "key_hash", normalized_hash)
        object.__setattr__(self, "project_id", normalized_project_id)
        object.__setattr__(self, "scopes", normalized_scopes)
        object.__setattr__(self, "key_id", normalized_key_id)
        object.__setattr__(self, "revoked", revoked)

    def allows(self, required_scope: ApiScope) -> bool:
        return ApiScope.ADMIN in self.scopes or required_scope in self.scopes

    def matches(self, api_key: str) -> bool:
        if self.revoked:
            return False
        try:
            candidate_hash = hash_api_key(api_key)
        except ValueError:
            return False
        return compare_digest(self.key_hash, candidate_hash)

    @property
    def rate_limit_id(self) -> str:
        if self.key_id is not None:
            return f"key_id:{self.key_id}"
        digest = self.key_hash.removeprefix(API_KEY_HASH_PREFIX)
        return f"key_hash_prefix:{digest[:16]}"


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Authenticated request context exposed to API handlers."""

    project_id: str
    scopes: frozenset[ApiScope]
    key_id: str | None = None
    rate_limit_id: str = ""

    @classmethod
    def from_credential(cls, credential: ApiKeyCredential) -> AuthenticatedPrincipal:
        return cls(
            project_id=credential.project_id,
            scopes=credential.scopes,
            key_id=credential.key_id,
            rate_limit_id=credential.rate_limit_id,
        )

    def allows(self, required_scope: ApiScope) -> bool:
        return ApiScope.ADMIN in self.scopes or required_scope in self.scopes


class ApiKeyStore:
    """In-memory API key lookup table."""

    def __init__(self, credentials: Iterable[ApiKeyCredential] = ()) -> None:
        self._credentials = tuple(credentials)

    def authenticate(self, api_key: str) -> AuthenticatedPrincipal | None:
        for credential in self._credentials:
            if credential.matches(api_key):
                return AuthenticatedPrincipal.from_credential(credential)
        return None


def hash_api_key(api_key: str) -> str:
    """Return the configured hash representation for an API key secret."""

    normalized_key = api_key.strip()
    if not normalized_key:
        raise ValueError("API key must not be empty")
    digest = sha256(normalized_key.encode("utf-8")).hexdigest()
    return f"{API_KEY_HASH_PREFIX}{digest}"


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
    key_hash = item.get("key_hash")
    project_id = item.get("project_id")
    scopes = item.get("scopes")
    key_id = item.get("key_id")
    revoked = item.get("revoked", False)
    if key is not None and not isinstance(key, str):
        raise ValueError("API key entry key must be a string")
    if key_hash is not None and not isinstance(key_hash, str):
        raise ValueError("API key entry key_hash must be a string")
    if not isinstance(project_id, str):
        raise ValueError("API key entry requires string project_id")
    if not isinstance(scopes, list):
        raise ValueError("API key entry requires list scopes")
    if not all(isinstance(scope, str) for scope in scopes):
        raise ValueError("API key scopes must be strings")
    if key_id is not None and not isinstance(key_id, str):
        raise ValueError("API key entry key_id must be a string")
    if not isinstance(revoked, bool):
        raise ValueError("API key entry revoked must be a boolean")

    return ApiKeyCredential(
        key=key,
        key_hash=key_hash,
        project_id=project_id,
        scopes=scopes,
        key_id=key_id,
        revoked=revoked,
    )


def _credential_hash_from_secret_or_hash(
    *,
    key: str | None,
    key_hash: str | None,
) -> str:
    if key is None and key_hash is None:
        raise ValueError("API key entry requires key or key_hash")
    if key is not None and key_hash is not None:
        raise ValueError("API key entry cannot include both key and key_hash")
    if key is not None:
        return hash_api_key(key)
    if key_hash is None:
        raise ValueError("API key entry requires key or key_hash")
    return _normalize_key_hash(key_hash)


def _normalize_key_hash(key_hash: str) -> str:
    normalized_hash = key_hash.strip().lower()
    if not normalized_hash:
        raise ValueError("API key hash must not be empty")
    if not normalized_hash.startswith(API_KEY_HASH_PREFIX):
        raise ValueError("API key hash must use sha256:<hex> format")
    digest = normalized_hash.removeprefix(API_KEY_HASH_PREFIX)
    if len(digest) != API_KEY_HASH_LENGTH or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("API key hash must use sha256:<hex> format")
    return f"{API_KEY_HASH_PREFIX}{digest}"
