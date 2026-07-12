"""Trend features: moving averages, MACD, ADX, RSI, rolling slope.

`ta`-library indicators here (EMA/SMA/MACD/ADX/RSI) are all trailing-only
by construction (Wilder's smoothing, exponential weighting, or a plain
trailing rolling window) — same library and same causality guarantee as
`regime-trader/data/feature_engineering.py`'s existing `trend_strength`
(ADX) and `rsi` functions, which this module's `adx_14`/`rsi_14` match
exactly.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd
import ta

from features.registry import FeatureCategory, feature


@feature("sma_20", FeatureCategory.TREND, lookback=20, description="20-bar simple moving average")
def sma_20(df: pd.DataFrame) -> pd.Series:
    return ta.trend.SMAIndicator(close=df["close"], window=20, fillna=False).sma_indicator()


@feature("sma_50", FeatureCategory.TREND, lookback=50, description="50-bar simple moving average")
def sma_50(df: pd.DataFrame) -> pd.Series:
    return ta.trend.SMAIndicator(close=df["close"], window=50, fillna=False).sma_indicator()


@feature(
    "ema_12", FeatureCategory.TREND, lookback=12, description="12-bar exponential moving average"
)
def ema_12(df: pd.DataFrame) -> pd.Series:
    return ta.trend.EMAIndicator(close=df["close"], window=12, fillna=False).ema_indicator()


@feature(
    "ema_26", FeatureCategory.TREND, lookback=26, description="26-bar exponential moving average"
)
def ema_26(df: pd.DataFrame) -> pd.Series:
    return ta.trend.EMAIndicator(close=df["close"], window=26, fillna=False).ema_indicator()


def _macd(df: pd.DataFrame) -> ta.trend.MACD:
    return ta.trend.MACD(
        close=df["close"], window_slow=26, window_fast=12, window_sign=9, fillna=False
    )


@feature(
    "macd_line",
    FeatureCategory.TREND,
    lookback=26,
    depends_on=("ema_12", "ema_26"),
    description="MACD line: EMA(12) - EMA(26)",
)
def macd_line(df: pd.DataFrame) -> pd.Series:
    return _macd(df).macd()


@feature(
    "macd_signal",
    FeatureCategory.TREND,
    lookback=34,
    depends_on=("macd_line",),
    description="MACD signal line: EMA(9) of the MACD line",
)
def macd_signal(df: pd.DataFrame) -> pd.Series:
    return _macd(df).macd_signal()


@feature(
    "macd_histogram",
    FeatureCategory.TREND,
    lookback=34,
    depends_on=("macd_line", "macd_signal"),
    description="MACD histogram: MACD line minus its signal line",
)
def macd_histogram(df: pd.DataFrame) -> pd.Series:
    return _macd(df).macd_diff()


_ADX_WINDOW = 14


@feature(
    "adx_14",
    FeatureCategory.TREND,
    lookback=2 * _ADX_WINDOW,
    description="Average Directional Index(14), Wilder's smoothing — trend strength, not direction",
)
def adx_14(df: pd.DataFrame) -> pd.Series:
    # ta.trend.ADXIndicator's internal `adx_series` array has length
    # `len(close) - (window - 1)`, and `adx()` unconditionally indexes
    # `adx_series[window]` -- so it raises IndexError (not a graceful NaN)
    # unless `len(close) - (window - 1) > window`, i.e. `len(df) >= 2 *
    # window`. Confirmed by direct boundary testing (window+1 rows still
    # crashes; 2*window is the true minimum). Every other feature in this
    # platform degrades to NaN for insufficient history via pandas'
    # `min_periods`/`NaN`-propagation conventions; this guard makes ADX
    # match that same contract instead of crashing the whole pipeline.
    if len(df) < 2 * _ADX_WINDOW:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return ta.trend.ADXIndicator(
        high=df["high"], low=df["low"], close=df["close"], window=_ADX_WINDOW, fillna=False
    ).adx()


@feature("rsi_14", FeatureCategory.TREND, lookback=15, description="Relative Strength Index(14)")
def rsi_14(df: pd.DataFrame) -> pd.Series:
    return ta.momentum.RSIIndicator(close=df["close"], window=14, fillna=False).rsi()


def _rolling_slope(close: pd.Series, window: int) -> pd.Series:
    """Trailing `window`-bar OLS slope of price vs. bar index, via the
    closed-form least-squares slope on the fixed relative-index vector
    `[0, 1, ..., window-1]` (only the trailing `window` prices vary
    between windows, so the design matrix's `x` term is precomputed once,
    not re-derived per window) — `raw=True` runs the inner function on a
    plain numpy array per window rather than a re-wrapped `pd.Series`,
    which matters for this feature's performance relative to the
    Milestone 3 targets (see `tests/features/test_performance.py`).
    """
    x = np.arange(window, dtype=float)
    x_demeaned = x - x.mean()
    denom = float(np.sum(x_demeaned**2))

    def _slope(values: npt.NDArray[np.float64]) -> float:
        y_demeaned = values - values.mean()
        return float(np.sum(x_demeaned * y_demeaned) / denom)

    return close.rolling(window=window, min_periods=window).apply(_slope, raw=True)


@feature(
    "slope_20",
    FeatureCategory.TREND,
    lookback=20,
    description="20-bar trailing OLS slope of close price vs. time",
)
def slope_20(df: pd.DataFrame) -> pd.Series:
    return _rolling_slope(df["close"], window=20)


__all__ = [
    "adx_14",
    "ema_12",
    "ema_26",
    "macd_histogram",
    "macd_line",
    "macd_signal",
    "rsi_14",
    "slope_20",
    "sma_20",
    "sma_50",
]
