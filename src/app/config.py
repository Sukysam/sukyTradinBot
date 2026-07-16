"""`MarketDataLoopConfig` -- what `MarketDataLoop` needs to know about
*which* symbols to poll and *how often*, separate from *how* to reach
Alpaca (that's `market_data.auth`/`ops.secrets`'s job) and separate from
business logic (there is none yet -- Phase A only fetches and logs).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from market_data.models import Timeframe


@dataclass(frozen=True)
class MarketDataLoopConfig:
    """Construction-time validated so a misconfigured loop fails at
    startup, not on its first poll."""

    symbols: tuple[str, ...]
    timeframe: Timeframe
    poll_interval_seconds: float
    lookback: timedelta

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if any(not symbol for symbol in self.symbols):
            raise ValueError("symbols must not contain an empty string")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self.lookback <= timedelta(0):
            raise ValueError("lookback must be positive")


@dataclass(frozen=True)
class FeatureLoopConfig:
    """What Phase B needs beyond `MarketDataLoopConfig`: how much bar
    history to retain per symbol for feature computation. `market_data`
    is composed, not duplicated -- Phase B still needs every Phase A
    setting (which symbols, how often)."""

    market_data: MarketDataLoopConfig
    max_bars_per_symbol: int = 200

    def __post_init__(self) -> None:
        if self.max_bars_per_symbol <= 0:
            raise ValueError("max_bars_per_symbol must be positive")


__all__ = ["FeatureLoopConfig", "MarketDataLoopConfig"]
