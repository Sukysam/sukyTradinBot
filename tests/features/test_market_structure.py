from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from features import market_structure
from features.pipeline import _bars_to_dataframe
from market_data.models import Bar, Timeframe
from tests.features.conftest import make_bars

UTC = timezone.utc


@pytest.fixture
def df() -> pd.DataFrame:
    return _bars_to_dataframe(make_bars(60))


def test_breakout_high_flags_new_high(df: pd.DataFrame) -> None:
    boosted = df.copy()
    boosted.loc[boosted.index[-1], "close"] = boosted["high"].iloc[:-1].max() * 1.1
    result = market_structure.breakout_high_20(boosted)
    assert result.iloc[-1] == 1.0


def test_breakout_high_not_flagged_mid_range(df: pd.DataFrame) -> None:
    flat = df.copy()
    flat.loc[flat.index[-1], "close"] = flat["close"].iloc[-21:-1].mean()
    result = market_structure.breakout_high_20(flat)
    assert result.iloc[-1] == 0.0


def test_breakout_low_flags_new_low(df: pd.DataFrame) -> None:
    dropped = df.copy()
    dropped.loc[dropped.index[-1], "close"] = dropped["low"].iloc[:-1].min() * 0.9
    result = market_structure.breakout_low_20(dropped)
    assert result.iloc[-1] == 1.0


def test_range_compression_below_one_when_range_narrows() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = []
    for i in range(20):
        bars.append(
            Bar(
                symbol="T",
                timestamp=start + timedelta(days=i),
                timeframe=Timeframe.DAY_1,
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1000,
            )
        )
    # Final bar has a much narrower range than the trailing average.
    bars.append(
        Bar(
            symbol="T",
            timestamp=start + timedelta(days=20),
            timeframe=Timeframe.DAY_1,
            open=100,
            high=100.5,
            low=99.5,
            close=100,
            volume=1000,
        )
    )
    df = _bars_to_dataframe(bars)
    result = market_structure.range_compression_14(df)
    assert result.iloc[-1] < 1.0


def test_swing_high_confirmed_detects_a_clean_peak() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    # Symmetric peak at index 5: rising then falling highs around it.
    highs = [100, 101, 102, 103, 104, 110, 104, 103, 102, 101, 100]
    bars = [
        Bar(
            symbol="T",
            timestamp=start + timedelta(days=i),
            timeframe=Timeframe.DAY_1,
            open=h - 1,
            high=h,
            low=h - 2,
            close=h - 1,
            volume=1000,
        )
        for i, h in enumerate(highs)
    ]
    df = _bars_to_dataframe(bars)
    result = market_structure.swing_high_confirmed(df)
    # Window size is 11 (2*5+1); the only fully-formed window ends at the
    # last bar (index 10), evaluating the candidate at index 5 (the peak).
    assert result.iloc[10] == 1.0


def test_swing_high_confirmed_uses_only_data_up_to_now(df: pd.DataFrame) -> None:
    """The defining anti-lookahead property: the signal at row t must be
    computable from data <= t. Perturbing a bar *after* the confirmation
    window closes must not change an already-emitted signal.
    """
    result_before = market_structure.swing_high_confirmed(df)
    truncated = df.iloc[:-1]
    result_truncated = market_structure.swing_high_confirmed(truncated)
    pd.testing.assert_series_equal(result_before.iloc[:-1], result_truncated, check_names=False)


def test_all_market_structure_features_aligned_to_input(df: pd.DataFrame) -> None:
    for func in (
        market_structure.breakout_high_20,
        market_structure.breakout_low_20,
        market_structure.range_compression_14,
        market_structure.swing_high_confirmed,
        market_structure.swing_low_confirmed,
    ):
        result = func(df)
        assert result.index.equals(df.index)
