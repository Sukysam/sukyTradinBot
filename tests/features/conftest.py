from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from market_data.models import Bar, Timeframe

UTC = timezone.utc


def make_bars(
    n: int,
    *,
    start: datetime = datetime(2024, 1, 1, tzinfo=UTC),
    delta: timedelta = timedelta(days=1),
    start_price: float = 100.0,
    seed: int = 42,
    timeframe: Timeframe = Timeframe.DAY_1,
    symbol: str = "TEST",
    drift: float = 0.0,
    vol: float = 0.01,
) -> list[Bar]:
    """`n` synthetic but internally consistent OHLCV bars (high >= max(o,c),
    low <= min(o,c)) driven by a seeded random walk — deterministic across
    runs, matching this repository's convention of never leaving test
    fixtures to real randomness.
    """
    rng = np.random.default_rng(seed)
    bars = []
    price = start_price
    for i in range(n):
        price *= 1 + drift + rng.normal(0, vol)
        price = max(price, 0.01)
        open_ = price * (1 + rng.normal(0, vol / 4))
        close = price
        high = max(open_, close) * (1 + abs(rng.normal(0, vol / 2)))
        low = min(open_, close) * (1 - abs(rng.normal(0, vol / 2)))
        volume = max(1.0, 1_000_000 + rng.normal(0, 50_000))
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=start + i * delta,
                timeframe=timeframe,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return bars


@pytest.fixture
def daily_bars() -> list[Bar]:
    """300 daily bars — enough trailing history for every registered
    feature's `lookback` (the largest is 100) to produce real values well
    before the end of the series.
    """
    return make_bars(300)
