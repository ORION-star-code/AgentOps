"""Local fixed-window rate limiting for authenticated API keys."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from threading import Lock
from time import monotonic
from typing import Callable


DEFAULT_RATE_LIMIT_PER_MINUTE = 600
RATE_LIMIT_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class RateLimitConfig:
    """Runtime rate limit configuration."""

    requests_per_window: int = DEFAULT_RATE_LIMIT_PER_MINUTE
    window_seconds: int = RATE_LIMIT_WINDOW_SECONDS

    def __post_init__(self) -> None:
        if self.requests_per_window < 0:
            raise ValueError("rate limit requests_per_window must not be negative")
        if self.window_seconds <= 0:
            raise ValueError("rate limit window_seconds must be positive")

    @property
    def enabled(self) -> bool:
        return self.requests_per_window > 0


@dataclass(frozen=True)
class RateLimitDecision:
    """Decision returned after checking one request against a limiter."""

    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int


class FixedWindowRateLimiter:
    """Thread-safe in-process fixed-window limiter keyed by credential identity."""

    def __init__(
        self,
        config: RateLimitConfig | None = None,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.config = config or RateLimitConfig()
        self._clock = clock
        self._lock = Lock()
        self._buckets: dict[str, tuple[int, int]] = {}

    def check(self, identity: str) -> RateLimitDecision:
        if not self.config.enabled:
            return RateLimitDecision(
                allowed=True,
                limit=0,
                remaining=0,
                reset_after_seconds=0,
            )

        now = self._clock()
        window_start = int(now // self.config.window_seconds) * self.config.window_seconds
        window_end = window_start + self.config.window_seconds
        with self._lock:
            bucket_window, count = self._buckets.get(identity, (window_start, 0))
            if bucket_window != window_start:
                bucket_window = window_start
                count = 0

            reset_after_seconds = max(0, ceil(window_end - now))
            if count >= self.config.requests_per_window:
                self._buckets[identity] = (bucket_window, count)
                return RateLimitDecision(
                    allowed=False,
                    limit=self.config.requests_per_window,
                    remaining=0,
                    reset_after_seconds=reset_after_seconds,
                )

            count += 1
            self._buckets[identity] = (bucket_window, count)
            return RateLimitDecision(
                allowed=True,
                limit=self.config.requests_per_window,
                remaining=self.config.requests_per_window - count,
                reset_after_seconds=reset_after_seconds,
            )


def load_rate_limit_config(raw_value: str | None) -> RateLimitConfig:
    """Load the local per-key rate limit from an environment variable value."""

    if raw_value is None or not raw_value.strip():
        return RateLimitConfig()

    normalized_value = raw_value.strip().lower()
    if normalized_value in {"0", "false", "off", "disabled"}:
        return RateLimitConfig(requests_per_window=0)

    try:
        requests_per_window = int(normalized_value)
    except ValueError as exc:
        raise ValueError("AGENTOPS_RATE_LIMIT_PER_MINUTE must be a non-negative integer") from exc

    return RateLimitConfig(requests_per_window=requests_per_window)
