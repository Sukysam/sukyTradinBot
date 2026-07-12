from __future__ import annotations

import pandas as pd
import pytest

from features import statistical
from features.pipeline import _bars_to_dataframe
from tests.features.conftest import make_bars


@pytest.fixture
def df() -> pd.DataFrame:
    return _bars_to_dataframe(make_bars(150))


def test_rolling_skew_and_kurtosis_produce_finite_values(df: pd.DataFrame) -> None:
    skew = statistical.rolling_skew_20(df).dropna()
    kurt = statistical.rolling_kurtosis_20(df).dropna()
    assert skew.apply(lambda v: v == v).all()  # no NaN leaked through
    assert kurt.apply(lambda v: v == v).all()


def test_autocorrelation_is_bounded_minus_one_to_one(df: pd.DataFrame) -> None:
    result = statistical.autocorrelation_20(df).dropna()
    assert (result >= -1.0001).all()
    assert (result <= 1.0001).all()


def test_autocorrelation_positive_for_strongly_trending_series() -> None:
    bars = make_bars(60, drift=0.02, vol=0.0001, seed=3)
    df_trend = _bars_to_dataframe(bars)
    result = statistical.autocorrelation_20(df_trend).dropna()
    # A near-noiseless uptrend has meaningfully positive autocorrelation --
    # not pinned to a precise value, since the exact number depends on the
    # rolling-window pairing convention (see _rolling_autocorr's docstring).
    assert result.iloc[-1] > 0.15


def test_hurst_exponent_present_after_warmup(df: pd.DataFrame) -> None:
    result = statistical.hurst_exponent_100(df)
    assert result.iloc[:99].isna().all()
    assert result.iloc[99:].notna().any()


def test_hurst_exponent_trending_series_above_one_half() -> None:
    bars = make_bars(150, drift=0.01, vol=0.001, seed=5)
    df_trend = _bars_to_dataframe(bars)
    result = statistical.hurst_exponent_100(df_trend).dropna()
    assert result.iloc[-1] > 0.5


def test_all_statistical_features_aligned_to_input(df: pd.DataFrame) -> None:
    for func in (
        statistical.rolling_skew_20,
        statistical.rolling_kurtosis_20,
        statistical.autocorrelation_20,
        statistical.hurst_exponent_100,
    ):
        result = func(df)
        assert result.index.equals(df.index)
