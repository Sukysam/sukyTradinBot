from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features import trend
from features.pipeline import _bars_to_dataframe
from tests.features.conftest import make_bars


@pytest.fixture
def df() -> pd.DataFrame:
    return _bars_to_dataframe(make_bars(120))


def test_sma_20_matches_manual_mean(df: pd.DataFrame) -> None:
    result = trend.sma_20(df)
    expected = df["close"].iloc[0:20].mean()
    assert result.iloc[19] == pytest.approx(expected)


def test_sma_50_matches_manual_mean(df: pd.DataFrame) -> None:
    result = trend.sma_50(df)
    expected = df["close"].iloc[0:50].mean()
    assert result.iloc[49] == pytest.approx(expected)


def test_ema_reacts_faster_than_sma_to_a_shock(df: pd.DataFrame) -> None:
    shocked = df.copy()
    shocked.loc[shocked.index[-1], "close"] = shocked["close"].iloc[-2] * 1.5
    ema = trend.ema_12(shocked)
    sma = trend.sma_20(shocked)
    ema_move = abs(ema.iloc[-1] - ema.iloc[-2])
    sma_move = abs(sma.iloc[-1] - sma.iloc[-2])
    assert ema_move > sma_move


def test_macd_line_equals_ema12_minus_ema26(df: pd.DataFrame) -> None:
    macd = trend.macd_line(df)
    manual = trend.ema_12(df) - trend.ema_26(df)
    pd.testing.assert_series_equal(macd, manual, check_names=False)


def test_macd_histogram_equals_line_minus_signal(df: pd.DataFrame) -> None:
    line = trend.macd_line(df)
    signal = trend.macd_signal(df)
    histogram = trend.macd_histogram(df)
    pd.testing.assert_series_equal(
        histogram.dropna(), (line - signal).dropna(), check_names=False, atol=1e-9
    )


def test_adx_14_is_bounded_0_to_100(df: pd.DataFrame) -> None:
    result = trend.adx_14(df).dropna()
    assert (result >= 0).all()
    assert (result <= 100).all()


def test_rsi_14_is_bounded_0_to_100(df: pd.DataFrame) -> None:
    result = trend.rsi_14(df).dropna()
    assert (result >= 0).all()
    assert (result <= 100).all()


def test_slope_20_positive_for_uptrend() -> None:
    bars = make_bars(40, drift=0.01, vol=0.0001, seed=1)
    df_up = _bars_to_dataframe(bars)
    result = trend.slope_20(df_up)
    assert result.dropna().iloc[-1] > 0


def test_slope_20_negative_for_downtrend() -> None:
    bars = make_bars(40, drift=-0.01, vol=0.0001, seed=1)
    df_down = _bars_to_dataframe(bars)
    result = trend.slope_20(df_down)
    assert result.dropna().iloc[-1] < 0


def test_slope_20_matches_numpy_polyfit(df: pd.DataFrame) -> None:
    result = trend.slope_20(df)
    window = df["close"].iloc[0:20].to_numpy()
    expected_slope = np.polyfit(np.arange(20), window, 1)[0]
    assert result.iloc[19] == pytest.approx(expected_slope)


def test_all_trend_features_aligned_to_input(df: pd.DataFrame) -> None:
    for func in (
        trend.sma_20,
        trend.sma_50,
        trend.ema_12,
        trend.ema_26,
        trend.macd_line,
        trend.macd_signal,
        trend.macd_histogram,
        trend.adx_14,
        trend.rsi_14,
        trend.slope_20,
    ):
        result = func(df)
        assert result.index.equals(df.index)
