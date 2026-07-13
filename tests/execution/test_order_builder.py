"""Tests for `execution.order_builder.OrderBuilder`."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from execution.models import ExecutionContext, FeatureSnapshot, OrderSide, OrderType
from execution.order_builder import OrderBuilder
from execution.stop_loss import ATRStopPolicy
from risk.models import Position
from tests.execution.conftest import (
    make_execution_context,
    make_execution_decision,
    make_feature_snapshot,
    make_portfolio_state,
)


@dataclass(frozen=True)
class _ConstantStopPolicy:
    """A `StopLossPolicy` test double returning a fixed value regardless
    of input -- used to exercise the builder's own "non-protective stop"
    guard."""

    stop_loss: float

    @property
    def name(self) -> str:
        return "constant_stop"

    def compute_stop_loss(
        self, context: ExecutionContext, feature_snapshot: FeatureSnapshot
    ) -> float:
        return self.stop_loss


class TestBuild:
    def test_returns_none_when_router_finds_no_action(self) -> None:
        builder = OrderBuilder(stop_loss_policy=ATRStopPolicy())
        decision = make_execution_decision(approved_allocation=0.1)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="TEST", sector="Tech", market_value=10_000.0),),
        )
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot()
        assert builder.build(decision, portfolio, context, snapshot) is None

    def test_builds_a_buy_with_stop_loss_from_policy(self) -> None:
        builder = OrderBuilder(stop_loss_policy=ATRStopPolicy(atr_multiplier=2.0))
        decision = make_execution_decision(approved_allocation=0.5)
        portfolio = make_portfolio_state(equity=100_000.0, positions=())
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot(atr_14=3.0)

        intent = builder.build(decision, portfolio, context, snapshot)

        assert intent is not None
        assert intent.side is OrderSide.BUY
        assert intent.order_type is OrderType.MARKET
        assert intent.reference_price == 100.0
        assert intent.stop_loss == pytest.approx(94.0)
        assert intent.take_profit is None
        assert intent.execution_reference == decision

    def test_builds_a_sell_with_no_stop_loss(self) -> None:
        builder = OrderBuilder(stop_loss_policy=ATRStopPolicy())
        decision = make_execution_decision(approved_allocation=0.0, strategy_allocation=0.0)
        portfolio = make_portfolio_state(
            equity=100_000.0,
            positions=(Position(ticker="TEST", sector="Tech", market_value=20_000.0),),
        )
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot()

        intent = builder.build(decision, portfolio, context, snapshot)

        assert intent is not None
        assert intent.side is OrderSide.SELL
        assert intent.stop_loss is None
        assert intent.take_profit is None

    def test_idempotency_key_is_deterministic(self) -> None:
        builder = OrderBuilder(stop_loss_policy=ATRStopPolicy())
        decision = make_execution_decision(approved_allocation=0.5)
        portfolio = make_portfolio_state(equity=100_000.0, positions=())
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot()

        first = builder.build(decision, portfolio, context, snapshot)
        second = builder.build(decision, portfolio, context, snapshot)

        assert first is not None and second is not None
        assert first.idempotency_key == second.idempotency_key

    def test_different_decisions_produce_different_idempotency_keys(self) -> None:
        builder = OrderBuilder(stop_loss_policy=ATRStopPolicy())
        portfolio = make_portfolio_state(equity=100_000.0, positions=())
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot()

        first = builder.build(
            make_execution_decision(approved_allocation=0.5, strategy_allocation=0.5),
            portfolio,
            context,
            snapshot,
        )
        second = builder.build(
            make_execution_decision(approved_allocation=0.6, strategy_allocation=0.6),
            portfolio,
            context,
            snapshot,
        )

        assert first is not None and second is not None
        assert first.idempotency_key != second.idempotency_key

    def test_raises_when_stop_policy_produces_non_protective_stop(self) -> None:
        builder = OrderBuilder(stop_loss_policy=_ConstantStopPolicy(stop_loss=100.0))
        decision = make_execution_decision(approved_allocation=0.5)
        portfolio = make_portfolio_state(equity=100_000.0, positions=())
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot()

        with pytest.raises(ValueError, match="non-protective"):
            builder.build(decision, portfolio, context, snapshot)

    def test_raises_on_context_symbol_mismatch(self) -> None:
        builder = OrderBuilder(stop_loss_policy=ATRStopPolicy())
        decision = make_execution_decision(symbol="TEST")
        portfolio = make_portfolio_state()
        context = make_execution_context(symbol="OTHER")
        snapshot = make_feature_snapshot(symbol="TEST")

        with pytest.raises(ValueError, match=r"context\.symbol"):
            builder.build(decision, portfolio, context, snapshot)

    def test_raises_on_feature_snapshot_symbol_mismatch(self) -> None:
        builder = OrderBuilder(stop_loss_policy=ATRStopPolicy())
        decision = make_execution_decision(symbol="TEST")
        portfolio = make_portfolio_state()
        context = make_execution_context(symbol="TEST")
        snapshot = make_feature_snapshot(symbol="OTHER")

        with pytest.raises(ValueError, match=r"feature_snapshot\.symbol"):
            builder.build(decision, portfolio, context, snapshot)

    def test_reasoning_mentions_strategy_id_and_quantity(self) -> None:
        builder = OrderBuilder(stop_loss_policy=ATRStopPolicy())
        decision = make_execution_decision(approved_allocation=0.5)
        portfolio = make_portfolio_state(equity=100_000.0, positions=())
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot()

        intent = builder.build(decision, portfolio, context, snapshot)

        assert intent is not None
        assert decision.strategy_reference.strategy_id in intent.reasoning
        assert str(intent.quantity) in intent.reasoning
