"""Regime features: volatility clustering, liquidity proxy.

**Scope note**: "correlation changes" (cross-asset/cross-symbol
correlation shifts) is deliberately not implemented in this milestone.
Every other feature in this platform is single-symbol — it's a pure
function of one symbol's own OHLCV history. Cross-symbol correlation
requires a second series as input, which the current pipeline contract
(`Sequence[Bar] -> FeatureVector`, one symbol per call) doesn't support.
Rather than register a misleadingly-named single-symbol proxy under
"correlation," this is tracked as a known, honest gap — see
docs/engineering-handbook/Architecture/ADR/ADR-003-Feature-Engineering.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from features.registry import FeatureCategory, feature


@feature(
    "volatility_clustering_20",
    FeatureCategory.REGIME,
    lookback=41,
    description="Trailing 20-bar lag-1 autocorrelation of squared 1-bar log returns (vol clustering)",
)
def volatility_clustering_20(df: pd.DataFrame) -> pd.Series:
    # See features.statistical._rolling_autocorr's docstring: native
    # Rolling.corr against a shifted series, not a Python-level .apply(),
    # for the same ~500x performance reason measured during Milestone 3.
    log_return_1 = np.log(df["close"] / df["close"].shift(1))
    squared_returns = log_return_1**2
    return squared_returns.rolling(window=20, min_periods=20).corr(squared_returns.shift(1))


@feature(
    "liquidity_proxy_20",
    FeatureCategory.REGIME,
    lookback=21,
    description="Trailing 20-bar Amihud illiquidity ratio: mean(|return| / dollar_volume)",
)
def liquidity_proxy_20(df: pd.DataFrame) -> pd.Series:
    log_return_1 = np.log(df["close"] / df["close"].shift(1))
    dollar_volume = df["close"] * df["volume"]
    daily_illiquidity = log_return_1.abs() / dollar_volume.replace(0, np.nan)
    return daily_illiquidity.rolling(window=20, min_periods=20).mean()


__all__ = ["liquidity_proxy_20", "volatility_clustering_20"]
