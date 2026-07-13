"""Tests for `execution.router`: buy/sell/hold determination and
whole-share quantity sizing."""

from __future__ import annotations

import pytest

from execution.models import OrderSide
from execution.router import MIN_ORDER_NOTIONAL, route
from risk.models import Position
from tests.execution.conftest import make_execution_decision, make_portfolio_state


class TestNoActionNeeded:
    def test_returns_none_when_target_matches_current_position(self) -> None:
        decision = make_execution_decision(approved_allocation=0.1)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="TEST", sector="Tech", market_value=10_000.0),),
        )
        assert route(decision, portfolio, reference_price=100.0) is None

    def test_returns_none_when_delta_below_min_notional(self) -> None:
        decision = make_execution_decision(approved_allocation=0.10001)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="TEST", sector="Tech", market_value=10_000.0),),
        )
        result = route(decision, portfolio, reference_price=100.0)
        assert result is None or abs(result.quantity * 100.0) >= MIN_ORDER_NOTIONAL

    def test_raises_on_non_positive_reference_price(self) -> None:
        decision = make_execution_decision()
        portfolio = make_portfolio_state()
        with pytest.raises(ValueError, match="reference_price"):
            route(decision, portfolio, reference_price=0.0)


class TestBuyRouting:
    def test_buy_when_no_existing_position(self) -> None:
        decision = make_execution_decision(approved_allocation=0.5)
        portfolio = make_portfolio_state(equity=100_000.0, positions=())
        result = route(decision, portfolio, reference_price=100.0)
        assert result is not None
        assert result.side is OrderSide.BUY
        assert result.quantity == 500  # 50,000 / 100

    def test_buy_tops_up_existing_position(self) -> None:
        decision = make_execution_decision(approved_allocation=0.5)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="TEST", sector="Tech", market_value=10_000.0),),
        )
        result = route(decision, portfolio, reference_price=100.0)
        assert result is not None
        assert result.side is OrderSide.BUY
        assert result.quantity == 400  # (50,000 - 10,000) / 100

    def test_buy_quantity_truncates_down(self) -> None:
        decision = make_execution_decision(approved_allocation=0.1)
        portfolio = make_portfolio_state(equity=100_000.0, positions=())
        result = route(decision, portfolio, reference_price=3.0)
        assert result is not None
        assert result.side is OrderSide.BUY
        assert result.quantity == 3333  # floor(10,000 / 3)


class TestSellRouting:
    def test_sell_when_target_below_current_position(self) -> None:
        decision = make_execution_decision(approved_allocation=0.0, strategy_allocation=0.0)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="TEST", sector="Tech", market_value=20_000.0),),
        )
        result = route(decision, portfolio, reference_price=100.0)
        assert result is not None
        assert result.side is OrderSide.SELL
        assert result.quantity == 200  # 20,000 / 100

    def test_sell_quantity_never_exceeds_current_position(self) -> None:
        decision = make_execution_decision(approved_allocation=0.0, strategy_allocation=0.0)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="TEST", sector="Tech", market_value=5_000.0),),
        )
        # reference price dropped a lot since the position was marked, so a
        # naive delta/price computation would oversell -- must be capped.
        result = route(decision, portfolio, reference_price=1.0)
        assert result is not None
        assert result.side is OrderSide.SELL
        assert result.quantity <= 5_000  # capped at current_value / reference_price


class TestOtherSymbolsIgnored:
    def test_only_the_decisions_own_symbol_counts_as_current_position(self) -> None:
        decision = make_execution_decision(symbol="TEST", approved_allocation=0.1)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="OTHER", sector="Tech", market_value=50_000.0),),
        )
        result = route(decision, portfolio, reference_price=100.0)
        assert result is not None
        assert result.side is OrderSide.BUY
        assert result.quantity == 100  # 10,000 / 100, OTHER's position is irrelevant
