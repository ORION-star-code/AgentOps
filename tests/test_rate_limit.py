from fastapi.testclient import TestClient

from agentops_api.audit import AuditOutcome
from agentops_api.main import create_app
from agentops_api.rate_limit import (
    FixedWindowRateLimiter,
    RateLimitConfig,
    load_rate_limit_config,
)
from agentops_api.security import ApiKeyCredential, ApiScope, ApiKeyStore, hash_api_key


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _client_with_limiter(
    db_path,
    *,
    requests_per_window: int,
    window_seconds: int = 60,
    clock: FakeClock | None = None,
    credentials: list[ApiKeyCredential] | None = None,
    include_auth_header: bool = True,
) -> TestClient:
    limiter = FixedWindowRateLimiter(
        RateLimitConfig(
            requests_per_window=requests_per_window,
            window_seconds=window_seconds,
        ),
        clock=clock or FakeClock(),
    )
    client = TestClient(
        create_app(
            db_path,
            api_keys=credentials
            or [
                ApiKeyCredential(
                    key="rate-key",
                    key_id="rate-key-id",
                    project_id="demo-project",
                    scopes=[ApiScope.READ],
                )
            ],
            rate_limiter=limiter,
        )
    )
    if include_auth_header:
        client.headers.update({"X-AgentOps-API-Key": "rate-key"})
    return client


def test_authenticated_v1_requests_are_rate_limited_per_key(tmp_path) -> None:
    client = _client_with_limiter(tmp_path / "agentops.db", requests_per_window=2)

    first = client.get("/v1/runs")
    second = client.get("/v1/runs")
    third = client.get("/v1/runs")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["detail"] == "Rate limit exceeded"
    assert third.headers["Retry-After"] == "60"
    assert third.headers["X-RateLimit-Limit"] == "2"
    assert third.headers["X-RateLimit-Remaining"] == "0"


def test_rate_limit_window_resets(tmp_path) -> None:
    clock = FakeClock()
    client = _client_with_limiter(
        tmp_path / "agentops.db",
        requests_per_window=1,
        window_seconds=10,
        clock=clock,
    )

    first = client.get("/v1/runs")
    blocked = client.get("/v1/runs")
    clock.advance(10)
    after_reset = client.get("/v1/runs")

    assert first.status_code == 200
    assert blocked.status_code == 429
    assert after_reset.status_code == 200


def test_rate_limit_isolated_by_api_key_identity(tmp_path) -> None:
    client = _client_with_limiter(
        tmp_path / "agentops.db",
        requests_per_window=1,
        credentials=[
            ApiKeyCredential(
                key="key-a",
                key_id="key-a-id",
                project_id="demo-project",
                scopes=[ApiScope.READ],
            ),
            ApiKeyCredential(
                key="key-b",
                key_id="key-b-id",
                project_id="demo-project",
                scopes=[ApiScope.READ],
            ),
        ],
    )

    first_key_a = client.get("/v1/runs", headers={"X-AgentOps-API-Key": "key-a"})
    second_key_a = client.get("/v1/runs", headers={"X-AgentOps-API-Key": "key-a"})
    first_key_b = client.get("/v1/runs", headers={"X-AgentOps-API-Key": "key-b"})

    assert first_key_a.status_code == 200
    assert second_key_a.status_code == 429
    assert first_key_b.status_code == 200


def test_rate_limit_can_be_disabled(tmp_path) -> None:
    client = _client_with_limiter(tmp_path / "agentops.db", requests_per_window=0)

    responses = [client.get("/v1/runs") for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 200]


def test_rate_limited_request_is_audited(tmp_path) -> None:
    client = _client_with_limiter(tmp_path / "agentops.db", requests_per_window=1)

    client.get("/v1/runs")
    blocked = client.get("/v1/runs")

    assert blocked.status_code == 429
    event = client.app.state.trace_repository.list_audit_events(project_id="demo-project")[0]
    assert event.key_id == "rate-key-id"
    assert event.scope == ApiScope.READ.value
    assert event.status_code == 429
    assert event.outcome == AuditOutcome.FAILED
    assert event.reason == "rate_limited"


def test_missing_or_invalid_keys_are_rejected_before_per_key_rate_limit(tmp_path) -> None:
    client = _client_with_limiter(
        tmp_path / "agentops.db",
        requests_per_window=1,
        include_auth_header=False,
    )

    missing = client.get("/v1/runs")
    invalid = client.get("/v1/runs", headers={"X-AgentOps-API-Key": "wrong-key"})
    valid = client.get("/v1/runs", headers={"X-AgentOps-API-Key": "rate-key"})

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert valid.status_code == 200


def test_rate_limit_config_loads_default_disabled_and_custom_values() -> None:
    assert load_rate_limit_config(None).requests_per_window == 600
    assert not load_rate_limit_config("0").enabled
    assert load_rate_limit_config("25").requests_per_window == 25


def test_rate_limit_identity_does_not_include_raw_key() -> None:
    credential = ApiKeyCredential(
        key="sensitive-rate-limit-key",
        project_id="demo-project",
        scopes=[ApiScope.READ],
    )
    principal = ApiKeyStore([credential]).authenticate("sensitive-rate-limit-key")

    assert principal is not None
    assert principal.rate_limit_id.startswith("key_hash_prefix:")
    assert "sensitive-rate-limit-key" not in principal.rate_limit_id
    assert hash_api_key("sensitive-rate-limit-key") not in principal.rate_limit_id
