from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common.time import FixedClock
from market_data.rate_limit import ALPACA_DEFAULT_REQUESTS_PER_MINUTE, RateLimiter


def _clock_at(seconds: float = 0.0) -> FixedClock:
    return FixedClock(datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc))


def test_rejects_non_positive_rate() -> None:
    with pytest.raises(ValueError, match="rate"):
        RateLimiter(rate=0, capacity=10)


def test_rejects_non_positive_capacity() -> None:
    with pytest.raises(ValueError, match="capacity"):
        RateLimiter(rate=10, capacity=0)


def test_starts_at_full_capacity() -> None:
    limiter = RateLimiter(rate=1.0, capacity=5.0, clock=_clock_at())
    assert limiter.try_acquire(5.0) is True


def test_try_acquire_fails_when_bucket_empty() -> None:
    limiter = RateLimiter(rate=1.0, capacity=1.0, clock=_clock_at())
    assert limiter.try_acquire(1.0) is True
    assert limiter.try_acquire(1.0) is False


def test_refills_over_time() -> None:
    clock = FixedClock(datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc))
    limiter = RateLimiter(rate=1.0, capacity=1.0, clock=clock)
    assert limiter.try_acquire(1.0) is True
    assert limiter.try_acquire(1.0) is False

    clock.advance(seconds=1.0)
    assert limiter.try_acquire(1.0) is True


def test_refill_never_exceeds_capacity() -> None:
    clock = FixedClock(datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc))
    limiter = RateLimiter(rate=10.0, capacity=5.0, clock=clock)
    clock.advance(seconds=100)  # would refill far past capacity without the cap
    assert limiter.try_acquire(5.0) is True
    assert limiter.try_acquire(0.01) is False


def test_acquire_blocks_via_injected_sleep_until_tokens_available() -> None:
    clock = FixedClock(datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc))
    limiter = RateLimiter(rate=1.0, capacity=1.0, clock=clock)
    limiter.try_acquire(1.0)  # drain the bucket

    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds=seconds)

    limiter.acquire(1.0, sleep=fake_sleep)

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(1.0)


def test_acquire_raises_if_requested_tokens_exceed_capacity() -> None:
    limiter = RateLimiter(rate=1.0, capacity=5.0, clock=_clock_at())
    with pytest.raises(ValueError, match="capacity"):
        limiter.acquire(10.0, sleep=lambda _: None)


def test_per_minute_constructor() -> None:
    limiter = RateLimiter.per_minute(ALPACA_DEFAULT_REQUESTS_PER_MINUTE)
    assert limiter.capacity == ALPACA_DEFAULT_REQUESTS_PER_MINUTE
    assert limiter.rate == pytest.approx(ALPACA_DEFAULT_REQUESTS_PER_MINUTE / 60.0)
