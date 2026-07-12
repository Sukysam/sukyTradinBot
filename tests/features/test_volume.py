from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features import volume
from features.pipeline import _bars_to_dataframe
from tests.features.conftest import make_bars


@pytest.fixture
def df() -> pd.DataFrame:
    return _bars_to_dataframe(make_bars(60))


def test_log_volume_matches_manual_log(df: pd.DataFrame) -> None:
    result = volume.log_volume(df)
    expected = np.log(df["volume"].clip(lower=1))
    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_rolling_vwap_is_between_low_and_high_of_window(df: pd.DataFrame) -> None:
    result = volume.rolling_vwap_20(df).dropna()
    window_low_max = df["low"].rolling(20, min_periods=20).min().dropna()
    window_high_max = df["high"].rolling(20, min_periods=20).max().dropna()
    assert (result >= window_low_max).all()
    assert (result <= window_high_max).all()


def test_obv_increases_on_up_bar_decreases_on_down_bar() -> None:
    from datetime import datetime, timedelta, timezone

    from market_data.models import Bar, Timeframe

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [
        Bar(
            symbol="T",
            timestamp=start,
            timeframe=Timeframe.DAY_1,
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000,
        ),
        Bar(
            symbol="T",
            timestamp=start + timedelta(days=1),
            timeframe=Timeframe.DAY_1,
            open=100,
            high=106,
            low=99,
            close=105,
            volume=500,
        ),  # up
        Bar(
            symbol="T",
            timestamp=start + timedelta(days=2),
            timeframe=Timeframe.DAY_1,
            open=105,
            high=106,
            low=99,
            close=100,
            volume=300,
        ),  # down
    ]
    df = _bars_to_dataframe(bars)
    result = volume.obv(df)
    assert result.iloc[0] == 0.0
    assert result.iloc[1] == 500.0  # +500 on up move
    assert result.iloc[2] == 200.0  # -300 on down move: 500 - 300


def test_volume_zscore_20_is_z_shaped(df: pd.DataFrame) -> None:
    result = volume.volume_zscore_20(df).dropna()
    # Not a strict statistical guarantee, but a z-score of well-behaved
    # synthetic data should mostly sit within a few standard deviations.
    assert result.abs().max() < 10


def test_relative_volume_excludes_current_bar(df: pd.DataFrame) -> None:
    result = volume.relative_volume_20(df)
    prior_mean = df["volume"].shift(1).rolling(20, min_periods=20).mean()
    expected = df["volume"] / prior_mean
    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_all_volume_features_aligned_to_input(df: pd.DataFrame) -> None:
    for func in (
        volume.log_volume,
        volume.rolling_vwap_20,
        volume.obv,
        volume.volume_zscore_20,
        volume.relative_volume_20,
    ):
        result = func(df)
        assert result.index.equals(df.index)
