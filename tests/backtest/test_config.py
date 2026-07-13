"""Tests for `backtest.config.BacktestConfig`'s construction-time
invariants."""

from __future__ import annotations

from datetime import timedelta

import pytest

from backtest.config import BacktestConfig
from tests.backtest.conftest import DEFAULT_START


def _config(**overrides: object) -> BacktestConfig:
    defaults: dict[str, object] = {
        "symbols": ("TEST",),
        "start_date": DEFAULT_START,
        "end_date": DEFAULT_START + timedelta(days=30),
    }
    defaults.update(overrides)
    return BacktestConfig(**defaults)  # type: ignore[arg-type]


class TestBacktestConfig:
    def test_rejects_empty_symbols(self) -> None:
        with pytest.raises(ValueError, match="symbols"):
            _config(symbols=())

    def test_rejects_end_date_not_after_start_date(self) -> None:
        with pytest.raises(ValueError, match="end_date"):
            _config(end_date=DEFAULT_START)

    def test_rejects_non_positive_initial_equity(self) -> None:
        with pytest.raises(ValueError, match="initial_equity"):
            _config(initial_equity=0.0)

    def test_rejects_non_positive_feature_lookback_bars(self) -> None:
        with pytest.raises(ValueError, match="feature_lookback_bars"):
            _config(feature_lookback_bars=0)

    def test_construction_succeeds_with_defaults(self) -> None:
        config = _config()
        assert config.dataset == "unspecified"
        assert config.sector_map == {}
