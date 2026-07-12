from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features import volatility
from features.pipeline import _bars_to_dataframe
from tests.features.conftest import make_bars


@pytest.fixture
def df() -> pd.DataFrame:
    return _bars_to_dataframe(make_bars(80))


def test_atr_14_is_non_negative(df: pd.DataFrame) -> None:
    result = volatility.atr_14(df)
    assert (result.dropna() >= 0).all()


def test_realized_volatility_matches_manual_stddev(df: pd.DataFrame) -> None:
    log_ret = np.log(df["close"] / df["close"].shift(1))
    result = volatility.realized_volatility_20(df)
    expected = log_ret.iloc[1:21].std()
    assert result.iloc[20] == pytest.approx(expected)


def test_parkinson_volatility_is_non_negative(df: pd.DataFrame) -> None:
    result = volatility.parkinson_volatility_20(df)
    assert (result.dropna() >= 0).all()


def test_parkinson_volatility_zero_when_high_equals_low(df: pd.DataFrame) -> None:
    flat = df.copy()
    flat["high"] = flat["close"]
    flat["low"] = flat["close"]
    result = volatility.parkinson_volatility_20(flat)
    assert result.dropna().eq(0).all()


def test_garman_klass_volatility_is_non_negative(df: pd.DataFrame) -> None:
    result = volatility.garman_klass_volatility_20(df)
    assert (result.dropna() >= 0).all()


def test_rolling_std_20_matches_manual_calculation(df: pd.DataFrame) -> None:
    result = volatility.rolling_std_20(df)
    expected = df["close"].iloc[0:20].std()
    assert result.iloc[19] == pytest.approx(expected)


def test_all_volatility_features_aligned_to_input(df: pd.DataFrame) -> None:
    for func in (
        volatility.atr_14,
        volatility.realized_volatility_20,
        volatility.parkinson_volatility_20,
        volatility.garman_klass_volatility_20,
        volatility.rolling_std_20,
    ):
        result = func(df)
        assert result.index.equals(df.index)
