"""Tests for `risk.sizing.ExposureCapacitySizing` -- must only ever reduce,
never increase, the requested allocation."""

from __future__ import annotations

import pytest

from risk.models import Position
from risk.sizing import ExposureCapacitySizing
from tests.risk.conftest import make_account_state, make_portfolio_state, make_strategy_decision


class TestExposureCapacitySizing:
    def test_ample_headroom_returns_requested_allocation_unchanged(self) -> None:
        decision = make_strategy_decision(allocation=0.1)
        portfolio = make_portfolio_state(equity=100_000.0)
        sized = ExposureCapacitySizing().apply(
            decision, decision.allocation, portfolio, make_account_state()
        )
        assert sized == decision.allocation

    def test_never_exceeds_requested_allocation(self) -> None:
        decision = make_strategy_decision(allocation=1.0)
        portfolio = make_portfolio_state(equity=100_000.0)
        sized = ExposureCapacitySizing().apply(
            decision, decision.allocation, portfolio, make_account_state()
        )
        assert sized <= decision.allocation

    def test_reduces_to_gross_exposure_headroom(self) -> None:
        decision = make_strategy_decision(allocation=0.5)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="X", sector="Tech", market_value=75_000.0),),
        )
        # 80% cap - 75% used = 5% headroom
        sized = ExposureCapacitySizing().apply(
            decision, decision.allocation, portfolio, make_account_state()
        )
        assert sized == pytest.approx(0.05)

    def test_reduces_to_single_ticker_headroom(self) -> None:
        decision = make_strategy_decision(symbol="AAPL", allocation=0.5)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="AAPL", sector="Tech", market_value=10_000.0),),
        )
        # 15% single-ticker cap - 10% used = 5% headroom, binding over 80% gross cap
        sized = ExposureCapacitySizing().apply(
            decision, decision.allocation, portfolio, make_account_state()
        )
        assert sized == pytest.approx(0.05)

    def test_reduces_to_sector_headroom_when_mapped(self) -> None:
        decision = make_strategy_decision(symbol="AAPL", allocation=0.5)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="MSFT", sector="Tech", market_value=25_000.0),),
        )
        sizing = ExposureCapacitySizing(sector_map={"AAPL": "Tech", "MSFT": "Tech"})
        # 30% sector cap - 25% used = 5% headroom
        sized = sizing.apply(decision, decision.allocation, portfolio, make_account_state())
        assert sized == pytest.approx(0.05)

    def test_unmapped_symbol_ignores_sector_headroom(self) -> None:
        decision = make_strategy_decision(symbol="ZZZZ", allocation=0.1)
        portfolio = make_portfolio_state(equity=100_000.0)
        sizing = ExposureCapacitySizing(sector_map={})
        sized = sizing.apply(decision, decision.allocation, portfolio, make_account_state())
        assert sized == decision.allocation

    def test_zero_headroom_never_negative(self) -> None:
        decision = make_strategy_decision(allocation=0.5)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="X", sector="Tech", market_value=100_000.0),),
        )
        sized = ExposureCapacitySizing().apply(
            decision, decision.allocation, portfolio, make_account_state()
        )
        assert sized == 0.0

    def test_deterministic(self) -> None:
        decision = make_strategy_decision(allocation=0.5)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="X", sector="Tech", market_value=75_000.0),),
        )
        sizing = ExposureCapacitySizing()
        results = {
            sizing.apply(decision, decision.allocation, portfolio, make_account_state())
            for _ in range(5)
        }
        assert len(results) == 1

    def test_non_positive_equity_yields_zero_headroom(self) -> None:
        decision = make_strategy_decision(allocation=0.5)
        portfolio = make_portfolio_state(equity=0.0)
        sized = ExposureCapacitySizing().apply(
            decision, decision.allocation, portfolio, make_account_state()
        )
        assert sized == 0.0

    def test_name(self) -> None:
        assert ExposureCapacitySizing().name == "exposure_capacity_sizing"
