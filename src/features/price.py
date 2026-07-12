"""Price features: returns, momentum, gaps.

Every function takes the full OHLCV DataFrame (columns
`open, high, low, close, volume`, ascending time index) and returns a
`pd.Series` aligned to the same index — the contract every registered
feature function follows (see `registry.FeatureFunc`). All are strictly
causal: output at row `t` depends only on rows `<= t`. `log_return_1`
matches `regime-trader/data/feature_engineering.log_returns(close, 1)`
exactly — extending, not replacing, that module's math.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from features.registry import FeatureCategory, feature


def _log_return(close: pd.Series, period: int) -> pd.Series:
    return np.log(close / close.shift(period))


@feature("returns_1", FeatureCategory.PRICE, lookback=2, description="1-bar simple percent return")
def returns_1(df: pd.DataFrame) -> pd.Series:
    return df["close"].pct_change(1)


@feature(
    "log_return_1", FeatureCategory.PRICE, lookback=2, description="1-bar log return: ln(C_t/C_t-1)"
)
def log_return_1(df: pd.DataFrame) -> pd.Series:
    return _log_return(df["close"], 1)


@feature(
    "log_return_5", FeatureCategory.PRICE, lookback=6, description="5-bar log return: ln(C_t/C_t-5)"
)
def log_return_5(df: pd.DataFrame) -> pd.Series:
    return _log_return(df["close"], 5)


@feature(
    "log_return_20",
    FeatureCategory.PRICE,
    lookback=21,
    description="20-bar log return: ln(C_t/C_t-20)",
)
def log_return_20(df: pd.DataFrame) -> pd.Series:
    return _log_return(df["close"], 20)


@feature(
    "rolling_return_20",
    FeatureCategory.PRICE,
    lookback=21,
    depends_on=("log_return_1",),
    description="Trailing 20-bar rolling mean of 1-bar log returns",
)
def rolling_return_20(df: pd.DataFrame) -> pd.Series:
    return _log_return(df["close"], 1).rolling(window=20, min_periods=20).mean()


@feature(
    "momentum_10",
    FeatureCategory.PRICE,
    lookback=11,
    description="10-bar rate-of-change momentum: 100 * (C_t - C_t-10) / C_t-10",
)
def momentum_10(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    return 100.0 * (close - close.shift(10)) / close.shift(10)


@feature(
    "momentum_20",
    FeatureCategory.PRICE,
    lookback=21,
    description="20-bar rate-of-change momentum: 100 * (C_t - C_t-20) / C_t-20",
)
def momentum_20(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    return 100.0 * (close - close.shift(20)) / close.shift(20)


@feature(
    "gap",
    FeatureCategory.PRICE,
    lookback=2,
    description="Opening gap vs. prior close: (O_t - C_t-1) / C_t-1",
)
def gap(df: pd.DataFrame) -> pd.Series:
    prior_close = df["close"].shift(1)
    return (df["open"] - prior_close) / prior_close


__all__ = [
    "gap",
    "log_return_1",
    "log_return_5",
    "log_return_20",
    "momentum_10",
    "momentum_20",
    "returns_1",
    "rolling_return_20",
]
