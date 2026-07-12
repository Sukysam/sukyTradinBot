"""Token-bucket rate limiting for provider API calls.

Generic — contains no Alpaca-specific knowledge beyond the default
constant below. Per docs/engineering-handbook/03_BACKEND_ENGINEER.md's
coding standards ("retry/backoff logic ... belongs at the client layer,
not scattered into call sites — one policy, one place"), the same applies
to rate limiting: one `RateLimiter` instance per provider client, never an
ad hoc `sleep()` scattered at call sites.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from common.interfaces import Clock
from common.time import SystemClock

# Alpaca's documented data API limit for free/paper accounts is 200
# requests/minute. Kept as an importable default so provider code doesn't
# hardcode it a second time, per the Python Style Guide's "named
# constants, not magic numbers."
ALPACA_DEFAULT_REQUESTS_PER_MINUTE = 200


@dataclass
class RateLimiter:
    """Token-bucket limiter: refills `rate` tokens/second up to `capacity`,
    and blocks the caller in `acquire()` until enough tokens exist.

    `clock` and the `sleep` callable passed to `acquire()` are both
    injectable so rate-limiting behavior is testable without a real test
    taking `capacity / rate` seconds to run — see
    `tests/market_data/test_rate_limit.py`, which pairs a
    `common.time.FixedClock` with a fake `sleep` that advances it.
    """

    rate: float
    capacity: float
    clock: Clock = field(default_factory=SystemClock)
    _tokens: float = field(init=False, repr=False)
    _last_refill: datetime = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError(f"rate must be > 0, got {self.rate}")
        if self.capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {self.capacity}")
        self._tokens = self.capacity
        self._last_refill = self.clock.now()

    @classmethod
    def per_minute(cls, requests_per_minute: float, clock: Clock | None = None) -> RateLimiter:
        """Convenience constructor: `requests_per_minute` sustained rate,
        with a burst capacity equal to one minute's worth of requests.
        """
        rate = requests_per_minute / 60.0
        return cls(rate=rate, capacity=requests_per_minute, clock=clock or SystemClock())

    def _refill(self) -> None:
        now = self.clock.now()
        elapsed_seconds = (now - self._last_refill).total_seconds()
        if elapsed_seconds > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed_seconds * self.rate)
        self._last_refill = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Non-blocking: consume `tokens` and return `True` if enough were
        available, otherwise leave the bucket untouched and return `False`.
        """
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def acquire(self, tokens: float = 1.0, *, sleep: Callable[[float], None] = time.sleep) -> None:
        """Blocking: wait until `tokens` are available, then consume them."""
        if tokens > self.capacity:
            raise ValueError(
                f"Requested {tokens} tokens exceeds bucket capacity {self.capacity}; "
                "this request can never succeed."
            )
        while not self.try_acquire(tokens):
            deficit = tokens - self._tokens
            wait_seconds = deficit / self.rate
            sleep(max(wait_seconds, 0.0))


__all__ = ["ALPACA_DEFAULT_REQUESTS_PER_MINUTE", "RateLimiter"]
