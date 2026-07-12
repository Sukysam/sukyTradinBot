from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common.time import FixedClock, SystemClock, utc_now


def test_system_clock_returns_timezone_aware_utc_now() -> None:
    result = SystemClock().now()
    assert result.tzinfo is not None
    assert result.utcoffset() == timezone.utc.utcoffset(None)


def test_utc_now_returns_timezone_aware_datetime() -> None:
    result = utc_now()
    assert result.tzinfo is not None


def test_fixed_clock_always_returns_same_instant() -> None:
    instant = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(instant)

    assert clock.now() == instant
    assert clock.now() == instant  # calling again must not advance it


def test_fixed_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(datetime(2026, 6, 1, 12, 0, 0))


def test_fixed_clock_advance_moves_time_forward() -> None:
    clock = FixedClock(datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc))
    clock.advance(seconds=90)
    assert clock.now() == datetime(2026, 6, 1, 12, 1, 30, tzinfo=timezone.utc)
