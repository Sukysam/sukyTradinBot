"""Contract tests for regime-trader/broker/alpaca_client.py.

Per docs/engineering-handbook/03_BACKEND_ENGINEER.md's acceptance
criteria: "alpaca_client.py ships with a contract test asserting its
return value satisfies MarketDataProvider: ascending time index, exactly
the columns ['open','high','low','close','volume'], no silent NaN gaps
within the requested lookback window."

Imports `broker.alpaca_client` the same way `regime-trader/main.py` does
(see the `pythonpath` entry for `regime-trader` in `pyproject.toml`) rather
than through a package name, since `regime-trader/` is not an installed
package.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from broker.alpaca_client import AlpacaMarketDataClient

from common.time import FixedClock
from market_data.interfaces import HistoricalDataProvider
from market_data.models import Bar, Timeframe

UTC = timezone.utc

# The two real lookback windows regime-trader/main.py actually calls this
# adapter with -- see FEATURE_HISTORY_LOOKBACK_DAYS and
# CORRELATION_HISTORY_LOOKBACK_DAYS in main.py, and
# 03_BACKEND_ENGINEER.md's pitfall note that both must return identically
# shaped data.
FEATURE_HISTORY_LOOKBACK_DAYS = 400
CORRELATION_HISTORY_LOOKBACK_DAYS = 90


def _bar(ts: datetime, close: float = 100.0) -> Bar:
    return Bar(
        symbol="AAPL",
        timestamp=ts,
        timeframe=Timeframe.DAY_1,
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=1_000_000.0,
    )


class _FakeProvider:
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars
        self.last_call: tuple[str, datetime, datetime, Timeframe] | None = None

    def get_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: Timeframe
    ) -> list[Bar]:
        self.last_call = (symbol, start, end, timeframe)
        return self._bars


def _client_with_bars(
    bars: list[Bar], clock: FixedClock | None = None
) -> tuple[AlpacaMarketDataClient, _FakeProvider]:
    provider = _FakeProvider(bars)
    client = AlpacaMarketDataClient(
        provider=provider, clock=clock or FixedClock(datetime(2026, 6, 1, tzinfo=UTC))
    )
    return client, provider


class TestContract:
    """The exact three properties main.py.MarketDataProvider requires."""

    def test_ascending_time_index(self) -> None:
        start = datetime(2026, 5, 1, tzinfo=UTC)
        shuffled = [
            _bar(start + timedelta(days=2)),
            _bar(start),
            _bar(start + timedelta(days=1)),
        ]
        client, _ = _client_with_bars(shuffled)

        df = client.get_ohlcv_history("AAPL", lookback_days=30)

        assert list(df.index) == sorted(df.index)

    def test_exactly_ohlcv_columns(self) -> None:
        start = datetime(2026, 5, 1, tzinfo=UTC)
        client, _ = _client_with_bars([_bar(start)])

        df = client.get_ohlcv_history("AAPL", lookback_days=30)

        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    def test_no_nan_gaps(self) -> None:
        start = datetime(2026, 5, 1, tzinfo=UTC)
        bars = [_bar(start + timedelta(days=i)) for i in range(10)]
        client, _ = _client_with_bars(bars)

        df = client.get_ohlcv_history("AAPL", lookback_days=30)

        assert not df.isna().any().any()

    def test_empty_result_still_has_correct_columns(self) -> None:
        client, _ = _client_with_bars([])

        df = client.get_ohlcv_history("AAPL", lookback_days=30)

        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 0


class TestLookbackTranslation:
    def test_translates_lookback_days_into_explicit_window(self) -> None:
        now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
        client, provider = _client_with_bars([], clock=FixedClock(now))

        client.get_ohlcv_history("AAPL", lookback_days=30)

        assert provider.last_call is not None
        symbol, start, end, timeframe = provider.last_call
        assert symbol == "AAPL"
        assert end == now
        assert start == now - timedelta(days=30)
        assert timeframe == Timeframe.DAY_1

    @pytest.mark.parametrize(
        "lookback_days", [FEATURE_HISTORY_LOOKBACK_DAYS, CORRELATION_HISTORY_LOOKBACK_DAYS]
    )
    def test_both_real_lookback_windows_return_identically_shaped_data(
        self, lookback_days: int
    ) -> None:
        """main.py calls get_ohlcv_history with two different lookback
        windows for two different purposes -- both must return data
        shaped identically regardless of window size (03_BACKEND_ENGINEER.md).
        """
        now = datetime(2026, 6, 15, tzinfo=UTC)
        bars = [_bar(now - timedelta(days=i)) for i in range(5)]
        client, provider = _client_with_bars(bars, clock=FixedClock(now))

        df = client.get_ohlcv_history("AAPL", lookback_days=lookback_days)

        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert provider.last_call is not None
        assert provider.last_call[1] == now - timedelta(days=lookback_days)


class TestDefaultConstruction:
    def test_default_provider_is_real_alpaca_historical_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Constructing with no arguments must not raise before credentials
        are actually needed -- AlpacaHistoricalProvider's own credential
        resolution is lazy per-client, not eager at AlpacaMarketDataClient
        construction time... this asserts the *type* wiring, not live
        network access (no real credentials are available in this
        environment -- see docs/engineering-handbook/Architecture/ADR/ADR-002-Market-Data.md).
        """
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

        client = AlpacaMarketDataClient()

        assert isinstance(client._provider, HistoricalDataProvider)


def test_dataframe_values_round_trip_correctly() -> None:
    ts = datetime(2026, 6, 1, tzinfo=UTC)
    bar = _bar(ts, close=150.25)
    client, _ = _client_with_bars([bar], clock=FixedClock(ts + timedelta(days=1)))

    df = client.get_ohlcv_history("AAPL", lookback_days=5)

    row = df.iloc[0]
    assert row["close"] == 150.25
    assert row["open"] == bar.open
    assert row["volume"] == bar.volume
    assert isinstance(df, pd.DataFrame)
