from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from features import price
from features.pipeline import _bars_to_dataframe
from tests.features.conftest import make_bars


@pytest.fixture
def df() -> pd.DataFrame:
    return _bars_to_dataframe(make_bars(60))


def test_returns_1_matches_pct_change(df: pd.DataFrame) -> None:
    result = price.returns_1(df)
    expected = (df["close"].iloc[10] - df["close"].iloc[9]) / df["close"].iloc[9]
    assert result.iloc[10] == pytest.approx(expected)
    assert pd.isna(result.iloc[0])


def test_log_return_1_matches_manual_calculation(df: pd.DataFrame) -> None:
    result = price.log_return_1(df)
    expected = math.log(df["close"].iloc[10] / df["close"].iloc[9])
    assert result.iloc[10] == pytest.approx(expected)


def test_log_return_5_uses_5_bar_lag(df: pd.DataFrame) -> None:
    result = price.log_return_5(df)
    expected = math.log(df["close"].iloc[10] / df["close"].iloc[5])
    assert result.iloc[10] == pytest.approx(expected)
    assert pd.isna(result.iloc[4])


def test_log_return_20_uses_20_bar_lag(df: pd.DataFrame) -> None:
    result = price.log_return_20(df)
    expected = math.log(df["close"].iloc[25] / df["close"].iloc[5])
    assert result.iloc[25] == pytest.approx(expected)


def test_rolling_return_20_is_mean_of_1_bar_returns(df: pd.DataFrame) -> None:
    log_ret_1 = np.log(df["close"] / df["close"].shift(1))
    result = price.rolling_return_20(df)
    expected = log_ret_1.iloc[10:30].mean()
    assert result.iloc[29] == pytest.approx(expected)


def test_momentum_10_matches_roc_formula(df: pd.DataFrame) -> None:
    result = price.momentum_10(df)
    expected = 100.0 * (df["close"].iloc[15] - df["close"].iloc[5]) / df["close"].iloc[5]
    assert result.iloc[15] == pytest.approx(expected)


def test_momentum_20_matches_roc_formula(df: pd.DataFrame) -> None:
    result = price.momentum_20(df)
    expected = 100.0 * (df["close"].iloc[25] - df["close"].iloc[5]) / df["close"].iloc[5]
    assert result.iloc[25] == pytest.approx(expected)


def test_gap_matches_open_vs_prior_close(df: pd.DataFrame) -> None:
    result = price.gap(df)
    expected = (df["open"].iloc[10] - df["close"].iloc[9]) / df["close"].iloc[9]
    assert result.iloc[10] == pytest.approx(expected)


def test_all_price_features_return_series_aligned_to_input(df: pd.DataFrame) -> None:
    for func in (
        price.returns_1,
        price.log_return_1,
        price.log_return_5,
        price.log_return_20,
        price.rolling_return_20,
        price.momentum_10,
        price.momentum_20,
        price.gap,
    ):
        result = func(df)
        assert isinstance(result, pd.Series)
        assert result.index.equals(df.index)
