"""Tests for `execution.models`: `OrderIntent`'s construction-time
invariants, plus `ExecutionContext`/`FeatureSnapshot`'s own light
validation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from execution.models import OrderIntent, OrderSide, OrderType, TimeInForce
from risk.models import ExecutionDecision
from tests.execution.conftest import (
    make_execution_context,
    make_execution_decision,
    make_feature_snapshot,
)

UTC = timezone.utc


def _intent(**overrides: object) -> OrderIntent:
    execution_decision = overrides.pop("execution_reference", None) or make_execution_decision()
    assert isinstance(execution_decision, ExecutionDecision)
    defaults: dict[str, object] = {
        "timestamp": execution_decision.timestamp,
        "symbol": execution_decision.symbol,
        "side": OrderSide.BUY,
        "quantity": 10,
        "order_type": OrderType.MARKET,
        "limit_price": None,
        "time_in_force": TimeInForce.DAY,
        "reference_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": None,
        "idempotency_key": "key-1",
        "reasoning": "test reasoning",
        "execution_reference": execution_decision,
        "metadata": {},
    }
    defaults.update(overrides)
    return OrderIntent(**defaults)  # type: ignore[arg-type]


class TestRequiredFields:
    def test_construction_succeeds_with_defaults(self) -> None:
        intent = _intent()
        assert intent.side is OrderSide.BUY
        assert intent.quantity == 10

    def test_symbol_must_match_execution_reference(self) -> None:
        with pytest.raises(ValueError, match="symbol"):
            _intent(symbol="OTHER")

    def test_timestamp_must_match_execution_reference(self) -> None:
        with pytest.raises(ValueError, match="timestamp"):
            _intent(timestamp=datetime(2025, 1, 1, tzinfo=UTC))

    def test_execution_reference_must_be_approved(self) -> None:
        rejected = make_execution_decision(approved=False)
        with pytest.raises(ValueError, match="approved"):
            _intent(execution_reference=rejected, side=OrderSide.SELL, stop_loss=None)

    def test_quantity_must_be_at_least_one(self) -> None:
        with pytest.raises(ValueError, match="quantity"):
            _intent(quantity=0)

    def test_reference_price_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="reference_price"):
            _intent(reference_price=0.0)


class TestOrderTypeInvariants:
    def test_market_order_forbids_limit_price(self) -> None:
        with pytest.raises(ValueError, match="limit_price"):
            _intent(order_type=OrderType.MARKET, limit_price=100.0)

    def test_limit_order_requires_positive_limit_price(self) -> None:
        with pytest.raises(ValueError, match="limit_price"):
            _intent(order_type=OrderType.LIMIT, limit_price=None)

    def test_limit_order_with_valid_price_succeeds(self) -> None:
        intent = _intent(order_type=OrderType.LIMIT, limit_price=99.5)
        assert intent.limit_price == 99.5


class TestStopLossInvariants:
    def test_buy_requires_stop_loss(self) -> None:
        with pytest.raises(ValueError, match="stop_loss"):
            _intent(side=OrderSide.BUY, stop_loss=None)

    def test_buy_stop_loss_must_be_below_reference_price(self) -> None:
        with pytest.raises(ValueError, match="stop_loss"):
            _intent(side=OrderSide.BUY, reference_price=100.0, stop_loss=100.0)

    def test_sell_forbids_stop_loss(self) -> None:
        with pytest.raises(ValueError, match="stop_loss"):
            _intent(side=OrderSide.SELL, stop_loss=95.0)

    def test_sell_with_no_stop_loss_succeeds(self) -> None:
        intent = _intent(side=OrderSide.SELL, stop_loss=None)
        assert intent.side is OrderSide.SELL

    def test_take_profit_must_be_above_reference_price_for_buy(self) -> None:
        with pytest.raises(ValueError, match="take_profit"):
            _intent(side=OrderSide.BUY, reference_price=100.0, stop_loss=95.0, take_profit=99.0)

    def test_sell_forbids_take_profit(self) -> None:
        with pytest.raises(ValueError, match="take_profit"):
            _intent(side=OrderSide.SELL, stop_loss=None, take_profit=105.0)


class TestStringFields:
    def test_idempotency_key_cannot_be_empty(self) -> None:
        with pytest.raises(ValueError, match="idempotency_key"):
            _intent(idempotency_key="")

    def test_reasoning_cannot_be_empty(self) -> None:
        with pytest.raises(ValueError, match="reasoning"):
            _intent(reasoning="")


class TestSerializationRoundTrip:
    def test_intent_round_trips_through_dict(self) -> None:
        intent = _intent(metadata={"note": "value"})
        assert OrderIntent.from_dict(intent.to_dict()) == intent

    def test_to_dict_is_json_serializable(self) -> None:
        import json

        json.dumps(_intent().to_dict())

    def test_sell_intent_round_trips(self) -> None:
        intent = _intent(side=OrderSide.SELL, stop_loss=None, take_profit=None)
        assert OrderIntent.from_dict(intent.to_dict()) == intent


class TestExecutionContext:
    def test_rejects_naive_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            make_execution_context(timestamp=datetime(2024, 1, 1))

    def test_rejects_non_positive_reference_price(self) -> None:
        with pytest.raises(ValueError, match="reference_price"):
            make_execution_context(reference_price=0.0)

    def test_rejects_non_positive_tick_size(self) -> None:
        with pytest.raises(ValueError, match="tick_size"):
            make_execution_context(tick_size=0.0)


class TestFeatureSnapshot:
    def test_rejects_negative_atr(self) -> None:
        with pytest.raises(ValueError, match="atr_14"):
            make_feature_snapshot(atr_14=-1.0)

    def test_rejects_negative_realized_volatility(self) -> None:
        with pytest.raises(ValueError, match="realized_volatility_20"):
            make_feature_snapshot(realized_volatility_20=-1.0)
