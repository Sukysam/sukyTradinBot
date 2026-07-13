"""Deterministic fixtures for `backtest` tests. Everything here is
synthetic -- never real historical market data, matching every other
milestone's own testing precedent (`tests/features/conftest.py::make_bars`,
`tests/hmm/`'s synthetic regime-switching series).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from features.pipeline import FeaturePipeline
from hmm.config import HMMConfig
from hmm.service import RegimeService
from market_data.models import Bar, Timeframe
from risk.service import RiskService
from strategy.config import StrategyEngineConfig
from strategy.registry import StrategyRegistry
from strategy.service import StrategyService
from strategy.strategies import (
    create_bear_strategy,
    create_defensive_strategy,
    create_growth_strategy,
)

UTC = timezone.utc
DEFAULT_START = datetime(2023, 1, 1, tzinfo=UTC)

#: The small feature subset used throughout `tests/backtest/` -- kept
#: intentionally minimal (well under `execution`'s own 21-bar realized-
#: volatility lookback) so a 60-bar `feature_lookback_bars` window is
#: comfortably enough for every feature used, HMM training included.
TEST_FEATURE_NAMES = ("returns_1", "atr_14", "rsi_14")


def make_bars(
    n: int,
    *,
    start: datetime = DEFAULT_START,
    delta: timedelta = timedelta(days=1),
    start_price: float = 100.0,
    seed: int = 42,
    symbol: str = "TEST",
    drift: float = 0.0002,
    vol: float = 0.01,
) -> list[Bar]:
    """`n` synthetic but internally consistent OHLCV bars, deterministic
    across runs -- matches `tests/features/conftest.py::make_bars`'s
    convention exactly (never real randomness in a fixture)."""
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
                timeframe=Timeframe.DAY_1,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return bars


def train_regime_service(
    bars: list[Bar], *, symbol: str = "TEST", model_version: str = "test_v1"
) -> RegimeService:
    pipeline = FeaturePipeline()
    vectors, _diagnostics = pipeline.compute_series(
        bars, symbol, feature_names=TEST_FEATURE_NAMES, source_dataset="test"
    )
    return RegimeService.train(
        vectors, symbol=symbol, model_version=model_version, config=HMMConfig()
    )


def make_strategy_service() -> StrategyService:
    registry = StrategyRegistry()
    registry.register(create_growth_strategy("growth_v1", frozenset({0})))
    registry.register(create_bear_strategy("bear_v1", frozenset({1})))
    registry.register(create_defensive_strategy("defensive_v1", frozenset()))
    return StrategyService(registry, StrategyEngineConfig(default_strategy_id="defensive_v1"))


def make_risk_service() -> RiskService:
    return RiskService.default()
