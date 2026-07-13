"""Tests for `execution.providers`: `BarSnapshotProvider` and
`FeaturePipelineSnapshotProvider`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from execution.providers import BarSnapshotProvider, FeaturePipelineSnapshotProvider
from market_data.models import Bar, Timeframe

UTC = timezone.utc


@dataclass(frozen=True)
class _FixedClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


def _make_bars(symbol: str, n: int, *, end: datetime, start_price: float = 100.0) -> list[Bar]:
    bars = []
    price = start_price
    for i in range(n):
        timestamp = end - timedelta(days=(n - i))
        price += 0.1  # gentle, deterministic drift
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=timestamp,
                timeframe=Timeframe.DAY_1,
                open=price - 0.5,
                high=price + 1.0,
                low=price - 1.0,
                close=price,
                volume=1_000_000.0,
            )
        )
    return bars


@dataclass(frozen=True)
class _FakeHistoricalDataProvider:
    bars: list[Bar]

    def get_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: Timeframe
    ) -> list[Bar]:
        return [b for b in self.bars if b.symbol == symbol and start <= b.timestamp < end]


class TestBarSnapshotProvider:
    def test_returns_context_from_most_recent_bar(self) -> None:
        now = datetime(2024, 3, 1, tzinfo=UTC)
        bars = _make_bars("TEST", 40, end=now)
        provider = BarSnapshotProvider(
            historical_provider=_FakeHistoricalDataProvider(bars=bars),
            clock=_FixedClock(now),
        )
        context = provider.get_snapshot("TEST")
        latest_bar = max(bars, key=lambda b: b.timestamp)
        assert context.symbol == "TEST"
        assert context.reference_price == latest_bar.close
        assert context.timestamp == latest_bar.timestamp
        assert context.price_source == "bar_close"
        assert context.bid is None
        assert context.ask is None
        assert context.spread is None

    def test_raises_when_no_bars_available(self) -> None:
        now = datetime(2024, 3, 1, tzinfo=UTC)
        provider = BarSnapshotProvider(
            historical_provider=_FakeHistoricalDataProvider(bars=[]),
            clock=_FixedClock(now),
        )
        with pytest.raises(ValueError, match="No bars available"):
            provider.get_snapshot("TEST")


class TestFeaturePipelineSnapshotProvider:
    def test_returns_snapshot_with_atr_and_realized_volatility(self) -> None:
        now = datetime(2024, 3, 1, tzinfo=UTC)
        bars = _make_bars("TEST", 40, end=now)
        provider = FeaturePipelineSnapshotProvider(
            historical_provider=_FakeHistoricalDataProvider(bars=bars),
            clock=_FixedClock(now),
        )
        snapshot = provider.get_latest("TEST")
        assert snapshot.symbol == "TEST"
        assert snapshot.atr_14 >= 0.0
        assert snapshot.realized_volatility_20 >= 0.0

    def test_raises_when_insufficient_bar_history(self) -> None:
        now = datetime(2024, 3, 1, tzinfo=UTC)
        bars = _make_bars("TEST", 5, end=now)
        provider = FeaturePipelineSnapshotProvider(
            historical_provider=_FakeHistoricalDataProvider(bars=bars),
            clock=_FixedClock(now),
        )
        with pytest.raises(ValueError, match="at least"):
            provider.get_latest("TEST")
