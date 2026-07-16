"""Tests for `app.config.MarketDataLoopConfig`'s construction-time
invariants."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import MarketDataLoopConfig
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
