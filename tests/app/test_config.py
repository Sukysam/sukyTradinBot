"""Tests for `app.config.MarketDataLoopConfig`'s construction-time
invariants."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import FeatureLoopConfig, MarketDataLoopConfig, RegimeLoopConfig
from market_data.models import Timeframe


def _config(**overrides: object) -> MarketDataLoopConfig:
    defaults: dict[str, object] = {
        "symbols": ("AAPL",),
        "timeframe": Timeframe.DAY_1,
        "poll_interval_seconds": 300.0,
        "lookback": timedelta(days=5),
    }
    defaults.update(overrides)
    return MarketDataLoopConfig(**defaults)  # type: ignore[arg-type]


class TestMarketDataLoopConfig:
    def test_valid_config_constructs(self) -> None:
        config = _config()
        assert config.symbols == ("AAPL",)

    def test_rejects_empty_symbols(self) -> None:
        with pytest.raises(ValueError, match="symbols"):
            _config(symbols=())

    def test_rejects_empty_string_symbol(self) -> None:
        with pytest.raises(ValueError, match="symbols"):
            _config(symbols=("AAPL", ""))

    def test_rejects_non_positive_poll_interval(self) -> None:
        with pytest.raises(ValueError, match="poll_interval_seconds"):
            _config(poll_interval_seconds=0.0)

    def test_rejects_negative_poll_interval(self) -> None:
        with pytest.raises(ValueError, match="poll_interval_seconds"):
            _config(poll_interval_seconds=-1.0)

    def test_rejects_non_positive_lookback(self) -> None:
        with pytest.raises(ValueError, match="lookback"):
            _config(lookback=timedelta(0))

    def test_is_frozen(self) -> None:
        config = _config()
        with pytest.raises(AttributeError):
            config.poll_interval_seconds = 60.0  # type: ignore[misc]


class TestFeatureLoopConfig:
    def test_valid_config_constructs_with_default_max_bars(self) -> None:
        config = FeatureLoopConfig(market_data=_config())
        assert config.max_bars_per_symbol == 200

    def test_rejects_non_positive_max_bars_per_symbol(self) -> None:
        with pytest.raises(ValueError, match="max_bars_per_symbol"):
            FeatureLoopConfig(market_data=_config(), max_bars_per_symbol=0)

    def test_is_frozen(self) -> None:
        config = FeatureLoopConfig(market_data=_config())
        with pytest.raises(AttributeError):
            config.max_bars_per_symbol = 50  # type: ignore[misc]


class TestRegimeLoopConfig:
    def test_valid_config_constructs_with_default_max_vectors(self) -> None:
        config = RegimeLoopConfig(feature_loop=FeatureLoopConfig(market_data=_config()))
        assert config.max_feature_vectors_per_symbol == 200

    def test_rejects_non_positive_max_feature_vectors_per_symbol(self) -> None:
        with pytest.raises(ValueError, match="max_feature_vectors_per_symbol"):
            RegimeLoopConfig(
                feature_loop=FeatureLoopConfig(market_data=_config()),
                max_feature_vectors_per_symbol=0,
            )

    def test_is_frozen(self) -> None:
        config = RegimeLoopConfig(feature_loop=FeatureLoopConfig(market_data=_config()))
        with pytest.raises(AttributeError):
            config.max_feature_vectors_per_symbol = 50  # type: ignore[misc]
