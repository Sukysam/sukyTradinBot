"""`BacktestConfig` -- run parameters for `backtest.engine.BacktestEngine.
run`. Deliberately not frozen as a contract (ADR-014 only freezes the
*output*, `BacktestResult`) -- this shape can evolve freely.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from common.time import require_utc
from market_data.models import Timeframe

DEFAULT_INITIAL_EQUITY = 100_000.0

#: Bars of history needed before `start_date` to fill both the HMM's own
#: inference window and `execution`'s ATR/realized-volatility lookback
#: (`_FEATURE_LOOKBACK_CALENDAR_DAYS` in `execution.providers`) -- see
#: ADR-015 for why this default was chosen.
DEFAULT_FEATURE_LOOKBACK_BARS = 60


@dataclass(frozen=True)
class BacktestConfig:
    symbols: tuple[str, ...]
    start_date: datetime
    end_date: datetime
    initial_equity: float = DEFAULT_INITIAL_EQUITY
    timeframe: Timeframe = Timeframe.DAY_1
    feature_lookback_bars: int = DEFAULT_FEATURE_LOOKBACK_BARS
    dataset: str = "unspecified"
    sector_map: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_utc(self.start_date, "start_date")
        require_utc(self.end_date, "end_date")
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if self.initial_equity <= 0:
            raise ValueError(f"initial_equity must be > 0, got {self.initial_equity}")
        if self.feature_lookback_bars < 1:
            raise ValueError(
                f"feature_lookback_bars must be >= 1, got {self.feature_lookback_bars}"
            )


__all__ = ["DEFAULT_FEATURE_LOOKBACK_BARS", "DEFAULT_INITIAL_EQUITY", "BacktestConfig"]
