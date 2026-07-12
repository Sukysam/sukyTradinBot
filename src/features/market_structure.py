"""Market structure features: breakouts, range compression, confirmed
swing points.

Swing-point detection is the one feature in this platform that would be
look-ahead-biased if implemented the "obvious" way: a swing high, in the
technical-analysis sense, is a bar whose high is greater than N bars
*before and after* it — which requires future data to confirm at the time
it happens. `swing_high_confirmed`/`swing_low_confirmed` below solve this
by reporting the signal on a deliberate lag: at time `t`, they answer "was
the bar `confirm_bars` ago a local extreme?", using only a window that
ends at `t` — see `_confirmed_swing`'s docstring for the derivation. This
is a real, worked example of the pattern
docs/engineering-handbook/Standards/Anti-Lookahead Checklist.md warns
about in the abstract.
"""

from __future__ import annotations

import pandas as pd

from features.registry import FeatureCategory, feature

_SWING_CONFIRM_BARS = 5


@feature(
    "breakout_high_20",
    FeatureCategory.MARKET_STRUCTURE,
    lookback=21,
    description="1.0 if close exceeds the prior 20 bars' highest high, else 0.0",
)
def breakout_high_20(df: pd.DataFrame) -> pd.Series:
    prior_high = df["high"].shift(1).rolling(window=20, min_periods=20).max()
    return (df["close"] > prior_high).astype(float)


@feature(
    "breakout_low_20",
    FeatureCategory.MARKET_STRUCTURE,
    lookback=21,
    description="1.0 if close falls below the prior 20 bars' lowest low, else 0.0",
)
def breakout_low_20(df: pd.DataFrame) -> pd.Series:
    prior_low = df["low"].shift(1).rolling(window=20, min_periods=20).min()
    return (df["close"] < prior_low).astype(float)


@feature(
    "range_compression_14",
    FeatureCategory.MARKET_STRUCTURE,
    lookback=14,
    description="Current bar range (high-low) relative to its trailing 14-bar mean; <1 = compressed",
)
def range_compression_14(df: pd.DataFrame) -> pd.Series:
    bar_range = df["high"] - df["low"]
    return bar_range / bar_range.rolling(window=14, min_periods=14).mean()


def _confirmed_swing(
    series: pd.Series, is_high: bool, confirm_bars: int = _SWING_CONFIRM_BARS
) -> pd.Series:
    """At time `t`, report whether the bar `confirm_bars` back was a local
    extreme within a `2*confirm_bars+1`-wide window centered on it — that
    window spans `[t - 2*confirm_bars, t]`, entirely `<= t`, so the signal
    is causal even though it describes a bar in the recent past rather
    than the current one.
    """
    window = 2 * confirm_bars + 1
    rolling_extreme = (
        series.rolling(window=window, min_periods=window).max()
        if is_high
        else series.rolling(window=window, min_periods=window).min()
    )
    candidate = series.shift(confirm_bars)
    return (candidate == rolling_extreme).astype(float)


@feature(
    "swing_high_confirmed",
    FeatureCategory.MARKET_STRUCTURE,
    lookback=2 * _SWING_CONFIRM_BARS + 1,
    description=f"1.0 if the high {_SWING_CONFIRM_BARS} bars ago was a confirmed local swing high",
)
def swing_high_confirmed(df: pd.DataFrame) -> pd.Series:
    return _confirmed_swing(df["high"], is_high=True)


@feature(
    "swing_low_confirmed",
    FeatureCategory.MARKET_STRUCTURE,
    lookback=2 * _SWING_CONFIRM_BARS + 1,
    description=f"1.0 if the low {_SWING_CONFIRM_BARS} bars ago was a confirmed local swing low",
)
def swing_low_confirmed(df: pd.DataFrame) -> pd.Series:
    return _confirmed_swing(df["low"], is_high=False)


__all__ = [
    "breakout_high_20",
    "breakout_low_20",
    "range_compression_14",
    "swing_high_confirmed",
    "swing_low_confirmed",
]
