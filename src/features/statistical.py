"""Statistical features: rolling skewness, kurtosis, autocorrelation, and
the Hurst exponent.

`hurst_exponent_100` is the most computationally involved feature in this
platform (classic rescaled-range/R-S estimation via log-log regression
across several sub-window sizes, re-run per row via a rolling window) —
see `tests/features/test_performance.py` for its measured cost against
the Milestone 3 performance targets.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd

from features.registry import FeatureCategory, feature


@feature(
    "rolling_skew_20",
    FeatureCategory.STATISTICAL,
    lookback=20,
    description="Trailing 20-bar skewness of 1-bar log returns",
)
def rolling_skew_20(df: pd.DataFrame) -> pd.Series:
    log_return_1 = np.log(df["close"] / df["close"].shift(1))
    return log_return_1.rolling(window=20, min_periods=20).skew()


@feature(
    "rolling_kurtosis_20",
    FeatureCategory.STATISTICAL,
    lookback=20,
    description="Trailing 20-bar excess kurtosis of 1-bar log returns",
)
def rolling_kurtosis_20(df: pd.DataFrame) -> pd.Series:
    log_return_1 = np.log(df["close"] / df["close"].shift(1))
    return log_return_1.rolling(window=20, min_periods=20).kurt()


def _rolling_autocorr(returns: pd.Series, window: int, lag: int = 1) -> pd.Series:
    """Rolling lag-`lag` autocorrelation via pandas' native `Rolling.corr`
    against the series shifted by `lag` — Cython-implemented, ~500x faster
    on 1-minute-bar-scale data than an equivalent `.rolling().apply()`
    with a Python callback per window (measured during Milestone 3's
    performance work; see `tests/features/test_performance.py`). Computes
    correlation between `returns[t-window+1:t+1]` and
    `returns[t-window-lag+1:t-lag+1]` at each `t` — the standard
    definition of rolling autocorrelation, not the same pairing as
    slicing consecutive values out of a single window, but an equally
    valid (and far more standard) one.
    """
    return returns.rolling(window=window, min_periods=window).corr(returns.shift(lag))


@feature(
    "autocorrelation_20",
    FeatureCategory.STATISTICAL,
    lookback=21,
    description="Trailing 20-bar lag-1 autocorrelation of 1-bar log returns",
)
def autocorrelation_20(df: pd.DataFrame) -> pd.Series:
    log_return_1 = np.log(df["close"] / df["close"].shift(1))
    return _rolling_autocorr(log_return_1, window=20, lag=1)


_HURST_SUB_WINDOW_SIZES = (10, 25, 50)


def _hurst_exponent(values: npt.NDArray[np.float64]) -> float:
    """Classic rescaled-range (R/S) Hurst exponent estimate for a fixed-
    length window: computes mean R/S at several sub-window sizes, then
    fits `H` as the slope of `log(R/S)` vs. `log(size)`. `H > 0.5`
    indicates trending/persistent behavior, `H < 0.5` mean-reverting,
    `H ~ 0.5` a random walk.

    Chunk statistics (mean, cumulative deviation, range, std) are computed
    with a single vectorized numpy reshape per sub-window size rather than
    a Python-level loop over chunks — called once per row via a rolling
    window (see `hurst_exponent_100` below), so this function's own cost
    dominates this platform's overall performance profile; see
    `tests/features/test_performance.py`.
    """
    n = len(values)
    max_size = n // 2
    sizes = [s for s in _HURST_SUB_WINDOW_SIZES if s <= max_size and n % s == 0]
    if len(sizes) < 2:
        return float("nan")

    log_sizes: list[float] = []
    log_rs: list[float] = []
    for size in sizes:
        n_chunks = n // size
        chunks = values[: n_chunks * size].reshape(n_chunks, size)
        deviations = chunks - chunks.mean(axis=1, keepdims=True)
        cumulative = np.cumsum(deviations, axis=1)
        r = cumulative.max(axis=1) - cumulative.min(axis=1)
        s = chunks.std(axis=1)
        valid = s > 0
        if valid.any():
            log_sizes.append(np.log(size))
            log_rs.append(np.log(np.mean(r[valid] / s[valid])))

    if len(log_sizes) < 2:
        return float("nan")

    slope, _ = np.polyfit(log_sizes, log_rs, 1)
    return float(slope)


@feature(
    "hurst_exponent_100",
    FeatureCategory.STATISTICAL,
    lookback=100,
    description="Trailing 100-bar Hurst exponent (rescaled-range method) of the raw close series",
)
def hurst_exponent_100(df: pd.DataFrame) -> pd.Series:
    return df["close"].rolling(window=100, min_periods=100).apply(_hurst_exponent, raw=True)


__all__ = [
    "autocorrelation_20",
    "hurst_exponent_100",
    "rolling_kurtosis_20",
    "rolling_skew_20",
]
