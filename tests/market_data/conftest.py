from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from market_data.models import Bar, Timeframe


@pytest.fixture
def utc_now() -> datetime:
    return datetime(2026, 6, 1, 9, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_bars(utc_now: datetime) -> list[Bar]:
    """10 consecutive 1-minute bars for AAPL, ascending timestamp order."""
    bars = []
    price = 100.0
    for i in range(10):
        bars.append(
            Bar(
                symbol="AAPL",
                timestamp=utc_now + timedelta(minutes=i),
                timeframe=Timeframe.MIN_1,
                open=price,
                high=price + 1.0,
                low=price - 1.0,
                close=price + 0.5,
                volume=1000.0 + i,
                trade_count=10 + i,
                vwap=price + 0.25,
            )
        )
        price += 0.5
    return bars
