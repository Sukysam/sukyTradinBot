"""Volume features: log volume, rolling VWAP, OBV, volume z-score,
relative volume.

`obv` (On-Balance Volume) is the one feature in this platform that is
genuinely cumulative rather than fixed-window — it sums signed volume from
the start of the provided history, not over a trailing `N`-bar window.
Still strictly causal (each value depends only on bars `<= t`), just with
an unbounded rather than fixed lookback; see its docstring.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from features.registry import FeatureCategory, feature


@feature(
    "log_volume",
    FeatureCategory.VOLUME,
    lookback=1,
    description="Log-transformed volume (variance-stabilized ahead of z-scoring)",
)
def log_volume(df: pd.DataFrame) -> pd.Series:
    return np.log(df["volume"].clip(lower=1))


@feature(
    "rolling_vwap_20",
    FeatureCategory.VOLUME,
    lookback=20,
    description="20-bar rolling volume-weighted average price",
)
def rolling_vwap_20(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical_price * df["volume"]
    return (
        pv.rolling(window=20, min_periods=20).sum()
        / df["volume"].rolling(window=20, min_periods=20).sum()
    )


@feature(
    "obv",
    FeatureCategory.VOLUME,
    lookback=2,
    description=(
        "On-Balance Volume: cumulative signed volume from the start of the "
        "provided history (expanding, not a fixed trailing window — see module docstring)"
    ),
)
def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff())
    signed_volume = direction * df["volume"]
    signed_volume.iloc[0] = 0.0  # first bar has no prior close to compare against
    return signed_volume.cumsum()


@feature(
    "volume_zscore_20",
    FeatureCategory.VOLUME,
    lookback=20,
    depends_on=("log_volume",),
    description="Trailing 20-bar rolling z-score of log volume",
)
def volume_zscore_20(df: pd.DataFrame) -> pd.Series:
    log_vol = np.log(df["volume"].clip(lower=1))
    rolling = log_vol.rolling(window=20, min_periods=20)
    zscore = (log_vol - rolling.mean()) / rolling.std()
    return zscore.replace([np.inf, -np.inf], np.nan)


@feature(
    "relative_volume_20",
    FeatureCategory.VOLUME,
    lookback=21,
    description="Current bar's volume relative to the mean of the prior 20 bars (excludes current bar)",
)
def relative_volume_20(df: pd.DataFrame) -> pd.Series:
    prior_mean = df["volume"].shift(1).rolling(window=20, min_periods=20).mean()
    return df["volume"] / prior_mean


__all__ = ["log_volume", "obv", "relative_volume_20", "rolling_vwap_20", "volume_zscore_20"]
