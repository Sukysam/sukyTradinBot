"""Volatility features: ATR, realized/Parkinson/Garman-Klass volatility,
rolling standard deviation.

All strictly causal — every rolling window uses `min_periods=window`, and
Parkinson/Garman-Klass are computed per-bar first, then rolling-averaged,
never using any bar after `t`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import ta

from features.registry import FeatureCategory, feature

_LOG_2 = np.log(2.0)
_ATR_WINDOW = 14


@feature(
    "atr_14",
    FeatureCategory.VOLATILITY,
    lookback=15,
    description="Average True Range(14), Wilder's smoothing, raw price units",
)
def atr_14(df: pd.DataFrame) -> pd.Series:
    # ta.volatility.AverageTrueRange indexes `[self._window - 1]` into an
    # internal array unconditionally, which raises IndexError (not a
    # graceful NaN) for fewer than `window` rows -- confirmed by direct
    # testing, the same underlying issue as adx_14's guard in trend.py.
    if len(df) < _ATR_WINDOW:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=_ATR_WINDOW, fillna=False
    ).average_true_range()


@feature(
    "realized_volatility_20",
    FeatureCategory.VOLATILITY,
    lookback=21,
    description="Trailing 20-bar stddev of 1-bar log returns",
)
def realized_volatility_20(df: pd.DataFrame) -> pd.Series:
    log_return_1 = np.log(df["close"] / df["close"].shift(1))
    return log_return_1.rolling(window=20, min_periods=20).std()


@feature(
    "parkinson_volatility_20",
    FeatureCategory.VOLATILITY,
    lookback=20,
    description="20-bar Parkinson volatility estimator (uses high/low range, not just close)",
)
def parkinson_volatility_20(df: pd.DataFrame) -> pd.Series:
    per_bar = np.log(df["high"] / df["low"]) ** 2
    mean_sq = per_bar.rolling(window=20, min_periods=20).mean()
    return np.sqrt(mean_sq / (4.0 * _LOG_2))


@feature(
    "garman_klass_volatility_20",
    FeatureCategory.VOLATILITY,
    lookback=20,
    description="20-bar Garman-Klass volatility estimator (uses full OHLC, more efficient than close-to-close)",
)
def garman_klass_volatility_20(df: pd.DataFrame) -> pd.Series:
    hl = 0.5 * np.log(df["high"] / df["low"]) ** 2
    co = (2.0 * _LOG_2 - 1.0) * np.log(df["close"] / df["open"]) ** 2
    per_bar = hl - co
    mean = per_bar.rolling(window=20, min_periods=20).mean()
    # Clip at 0 before sqrt: a pathological single bar (e.g. open == close
    # with a huge high/low range) can theoretically drive the windowed mean
    # very slightly negative; treat that as "no measurable GK variance" for
    # that window rather than emitting NaN from sqrt of a negative number.
    return np.sqrt(mean.clip(lower=0.0))


@feature(
    "rolling_std_20",
    FeatureCategory.VOLATILITY,
    lookback=20,
    description="Trailing 20-bar standard deviation of raw close price",
)
def rolling_std_20(df: pd.DataFrame) -> pd.Series:
    return df["close"].rolling(window=20, min_periods=20).std()


__all__ = [
    "atr_14",
    "garman_klass_volatility_20",
    "parkinson_volatility_20",
    "realized_volatility_20",
    "rolling_std_20",
]
