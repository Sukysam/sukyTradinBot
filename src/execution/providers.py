"""Concrete `MarketSnapshotProvider`/`FeatureSnapshotProvider`
implementations.

Both wrap `market_data.interfaces.HistoricalDataProvider` -- never a
specific provider like `AlpacaHistoricalProvider` directly, and never
`alpaca-py` -- so this module stays broker-agnostic, matching the rest of
`src/execution`. `market_data`/`features` are this platform's own
packages, not a specific broker's SDK; depending on them here is the same
relationship `hmm` already has with `features`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from common.interfaces import Clock
from common.time import SystemClock
from execution.models import ExecutionContext, FeatureSnapshot
from features.pipeline import FeaturePipeline
from market_data.interfaces import HistoricalDataProvider
from market_data.models import Timeframe

#: A conservative default for US equities; a real venue-specific tick
#: table is future work (see ADR-013's Consequences) -- this constant is
#: an honest placeholder, not a fabricated precision claim.
DEFAULT_TICK_SIZE = 0.01

#: Feature lookback: `atr_14`'s own window is 14 bars, `realized_
#: volatility_20`'s is 20 -- 30 bars of buffer comfortably covers both
#: plus a few bars of warm-up slack.
_FEATURE_LOOKBACK_BARS = 30
_FEATURE_LOOKBACK_CALENDAR_DAYS = 60  # generous enough to cover weekends/holidays
_FEATURE_NAMES = ("atr_14", "realized_volatility_20")


@dataclass(frozen=True)
class BarSnapshotProvider:
    """`MarketSnapshotProvider` sourced from the most recent daily bar.

    Honest about what it can't supply: `bid`/`ask`/`spread` are always
    `None` -- a `Bar` carries no quote data, only OHLCV. A future
    `MarketSnapshotProvider` backed by `market_data.interfaces.
    StreamingDataProvider`'s live quotes could populate them; this one
    deliberately doesn't guess.
    """

    historical_provider: HistoricalDataProvider
    clock: Clock = field(default_factory=SystemClock)
    timeframe: Timeframe = Timeframe.DAY_1
    tick_size: float = DEFAULT_TICK_SIZE

    def get_snapshot(self, symbol: str) -> ExecutionContext:
        now = self.clock.now()
        start = now - timedelta(days=_FEATURE_LOOKBACK_CALENDAR_DAYS)
        bars = self.historical_provider.get_bars(symbol, start, now, self.timeframe)
        if not bars:
            raise ValueError(f"No bars available for {symbol!r} in [{start}, {now})")
        latest = max(bars, key=lambda b: b.timestamp)
        return ExecutionContext(
            symbol=symbol,
            timestamp=latest.timestamp,
            reference_price=latest.close,
            bid=None,
            ask=None,
            spread=None,
            tick_size=self.tick_size,
            price_source="bar_close",
        )


@dataclass(frozen=True)
class FeaturePipelineSnapshotProvider:
    """`FeatureSnapshotProvider` sourced from a fresh `FeaturePipeline`
    run over recent bars -- computes only `atr_14`/`realized_
    volatility_20` (`feature_names=` restricts the pipeline to exactly
    what `FeatureSnapshot` needs), not a full `FeatureVector`.
    """

    historical_provider: HistoricalDataProvider
    clock: Clock = field(default_factory=SystemClock)
    timeframe: Timeframe = Timeframe.DAY_1
    pipeline: FeaturePipeline = field(default_factory=FeaturePipeline)

    def get_latest(self, symbol: str) -> FeatureSnapshot:
        now = self.clock.now()
        start = now - timedelta(days=_FEATURE_LOOKBACK_CALENDAR_DAYS)
        bars = self.historical_provider.get_bars(symbol, start, now, self.timeframe)
        if len(bars) < _FEATURE_LOOKBACK_BARS:
            raise ValueError(
                f"Need at least {_FEATURE_LOOKBACK_BARS} bars to compute a reliable "
                f"FeatureSnapshot for {symbol!r}, got {len(bars)}"
            )
        vectors, _diagnostics = self.pipeline.compute_series(
            bars, symbol, feature_names=_FEATURE_NAMES, source_dataset="execution_snapshot"
        )
        latest = vectors[-1]
        values = dict(zip(latest.feature_names, latest.feature_values))
        return FeatureSnapshot(
            symbol=symbol,
            timestamp=latest.timestamp,
            atr_14=values["atr_14"],
            realized_volatility_20=values["realized_volatility_20"],
        )


__all__ = ["BarSnapshotProvider", "FeaturePipelineSnapshotProvider"]
