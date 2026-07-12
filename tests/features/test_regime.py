from __future__ import annotations

import pandas as pd
import pytest

from features import regime
from features.pipeline import _bars_to_dataframe
from tests.features.conftest import make_bars


@pytest.fixture
def df() -> pd.DataFrame:
    return _bars_to_dataframe(make_bars(80))


def test_volatility_clustering_bounded(df: pd.DataFrame) -> None:
    result = regime.volatility_clustering_20(df).dropna()
    assert (result >= -1.0001).all()
    assert (result <= 1.0001).all()


def test_liquidity_proxy_non_negative(df: pd.DataFrame) -> None:
    result = regime.liquidity_proxy_20(df).dropna()
    assert (result >= 0).all()


def test_liquidity_proxy_higher_for_thinner_dollar_volume() -> None:
    thin = make_bars(60, seed=1)
    thick = make_bars(60, seed=1)
    thick_df = _bars_to_dataframe(thick)
    thick_df["volume"] = thick_df["volume"] * 100  # much higher dollar volume, same returns
    thin_df = _bars_to_dataframe(thin)

    thin_result = regime.liquidity_proxy_20(thin_df).dropna().iloc[-1]
    thick_result = regime.liquidity_proxy_20(thick_df).dropna().iloc[-1]
    assert thin_result > thick_result


def test_all_regime_features_aligned_to_input(df: pd.DataFrame) -> None:
    for func in (regime.volatility_clustering_20, regime.liquidity_proxy_20):
        result = func(df)
        assert result.index.equals(df.index)
