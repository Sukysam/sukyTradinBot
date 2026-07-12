"""Alpaca historical OHLCV client — closes Known Gaps item 2 (Spec-adjacent:
satisfies `main.py.MarketDataProvider`).

Thin adapter over `market_data.providers.alpaca_historical.
AlpacaHistoricalProvider` (Milestone 2's provider-agnostic Alpaca bars
provider, see docs/engineering-handbook/Architecture/ADR/ADR-002-Market-Data.md):
translates `get_ohlcv_history`'s `lookback_days` contract into an explicit
`[start, end)` window (using an injected `common.interfaces.Clock` for
"now", never `datetime.now()` directly, matching
docs/engineering-handbook/Standards/Python Style Guide.md's "pass 'now' as
an explicit parameter" convention), fetches daily bars, and reshapes the
result into the ascending-time-indexed DataFrame
`data/feature_engineering.py`'s `build_feature_matrix` expects.

Deliberately contains no retry, rate-limiting, or credential logic of its
own — all of that already lives in `AlpacaHistoricalProvider`. This
adapter's only job is the `Protocol`-shape translation between the
`market_data` package and `regime-trader/main.py`'s existing contract, per
docs/engineering-handbook/03_BACKEND_ENGINEER.md's coding standard that
"retry/backoff logic for transient API errors belongs at the client
layer... one policy, one place" — that place is `AlpacaHistoricalProvider`,
not here, so this file doesn't duplicate it.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from common.interfaces import Clock
from common.time import SystemClock
from market_data.interfaces import HistoricalDataProvider
from market_data.models import Timeframe
from market_data.providers.alpaca_historical import AlpacaHistoricalProvider

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class AlpacaMarketDataClient:
    """Satisfies `main.py.MarketDataProvider`.

    `provider` and `clock` are injectable per this repository's
    dependency-injection convention (see
    docs/engineering-handbook/Architecture/ADR/ADR-001-Foundation.md
    Decision 4) — a test supplies a fake `HistoricalDataProvider` and a
    `common.time.FixedClock` instead of hitting the real Alpaca API or
    depending on wall-clock time.
    """

    def __init__(
        self,
        provider: HistoricalDataProvider | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._provider = provider or AlpacaHistoricalProvider()
        self._clock = clock or SystemClock()

    def get_ohlcv_history(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        """Ascending-time-indexed OHLCV DataFrame with columns
        ['open','high','low','close','volume'] — see
        `main.py.MarketDataProvider`'s contract docstring, which this
        method must match exactly (both `FEATURE_HISTORY_LOOKBACK_DAYS=400`
        and `CORRELATION_HISTORY_LOOKBACK_DAYS=90` call sites depend on it).
        """
        end = self._clock.now()
        start = end - timedelta(days=lookback_days)

        bars = self._provider.get_bars(ticker, start, end, Timeframe.DAY_1)

        if not bars:
            return pd.DataFrame(columns=_OHLCV_COLUMNS)

        records = [
            {
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
        frame = pd.DataFrame.from_records(records, index="timestamp")
        return frame.sort_index()[_OHLCV_COLUMNS]


__all__ = ["AlpacaMarketDataClient"]
