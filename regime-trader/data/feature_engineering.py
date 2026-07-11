"""Pure, deterministic feature transformations for the HMM Volatility Engine.

Every function is strictly causal: the output at index t depends only on rows
at or before t. No rolling window here uses center=True, no shift is negative,
and z-score normalization is trailing-only. This module is the single point of
truth for anti-look-ahead compliance in the feature pipeline (Spec Sec. 2).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import ta

ZSCORE_WINDOW = 252
REQUIRED_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def _require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Input DataFrame missing required columns: {missing}")


def log_returns(close: pd.Series, period: int) -> pd.Series:
    """Log return over `period` bars: ln(C_t / C_{t-period})."""
    if period < 1:
        raise ValueError("period must be >= 1")
    return np.log(close / close.shift(period))


def rolling_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    """Trailing rolling stddev of 1-period log returns."""
    return log_returns(close, 1).rolling(window=window, min_periods=window).std()


def log_volume(volume: pd.Series) -> pd.Series:
    """Log-transformed volume; stabilizes variance ahead of z-score normalization."""
    return np.log(volume.clip(lower=1))


def trend_strength(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """ADX(window) via `ta` — Wilder's smoothing is trailing-only by construction."""
    return ta.trend.ADXIndicator(high=high, low=low, close=close, window=window, fillna=False).adx()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """RSI(window) via `ta`."""
    return ta.momentum.RSIIndicator(close=close, window=window, fillna=False).rsi()


def momentum(close: pd.Series, window: int = 20) -> pd.Series:
    """Rate-of-change momentum over `window` bars, distinct from the log-return features."""
    return ta.momentum.ROCIndicator(close=close, window=window, fillna=False).roc()


def average_true_range(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """ATR(window) via `ta`. Kept in raw (unnormalized) price units for use in stop-loss math."""
    return ta.volatility.AverageTrueRange(
        high=high, low=low, close=close, window=window, fillna=False
    ).average_true_range()


def rolling_zscore(series: pd.Series, window: int = ZSCORE_WINDOW) -> pd.Series:
    """Trailing rolling z-score: (x_t - mean_{t-window+1:t}) / std_{t-window+1:t}.

    min_periods=window means no value is emitted until a full trailing window
    exists, so early-history bars never get a normalized value derived from a
    partial (and therefore statistically unstable) sample.
    """
    rolling = series.rolling(window=window, min_periods=window)
    zscore = (series - rolling.mean()) / rolling.std()
    return zscore.replace([np.inf, -np.inf], np.nan)


def build_feature_matrix(df: pd.DataFrame, zscore_window: int = ZSCORE_WINDOW) -> pd.DataFrame:
    """Construct the full HMM feature matrix from an OHLCV DataFrame.

    `df` must be indexed by time, ascending, with columns
    ['open', 'high', 'low', 'close', 'volume']. Returns raw features (suffix-free,
    kept for downstream strategy/stop-loss use — e.g. raw ATR, raw close) plus
    their 252-day rolling z-score normalized counterparts (suffix `_z`), which
    are what should be fed to `hmm_engine.py`.
    """
    _require_columns(df, REQUIRED_OHLCV_COLUMNS)

    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    raw = pd.DataFrame(index=df.index)
    raw["log_return_1"] = log_returns(close, 1)
    raw["log_return_5"] = log_returns(close, 5)
    raw["log_return_20"] = log_returns(close, 20)
    raw["volatility_20"] = rolling_volatility(close, window=20)
    raw["log_volume"] = log_volume(volume)
    raw["adx_14"] = trend_strength(high, low, close, window=14)
    raw["rsi_14"] = rsi(close, window=14)
    raw["momentum_20"] = momentum(close, window=20)
    raw["atr_14"] = average_true_range(high, low, close, window=14)

    normalized = pd.DataFrame(index=df.index)
    for col in raw.columns:
        normalized[f"{col}_z"] = rolling_zscore(raw[col], window=zscore_window)

    return pd.concat([raw, normalized], axis=1)
