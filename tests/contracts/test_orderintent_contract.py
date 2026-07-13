"""Regression tests for the `OrderIntent` contract itself (Standards/
OrderIntent Contract.md), distinct from `tests/execution/`'s own unit
tests -- these exist to catch an accidental breaking change to the
contract's *shape*, not to test routing/stop-loss/broker logic. If a
change here forces an edit to this file, that's a signal the change
needs a new ADR per that Standards document's own versioning policy.
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone

import pytest

from execution.models import OrderIntent, OrderSide, OrderType, TimeInForce
from risk.models import DecisionType, ExecutionDecision
from strategy.models import StrategyDecision

UTC = timezone.utc


def _strategy_decision(**overrides: object) -> StrategyDecision:
    defaults: dict[str, object] = {
        "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
        "symbol": "AAPL",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "allocation": 0.5,
        "confidence": 0.8,
        "expected_holding_period": timedelta(days=5),
        "reasoning": "test reasoning",
        "metadata": {},
    }
    defaults.update(overrides)
    return StrategyDecision(**defaults)  # type: ignore[arg-type]


def _execution_decision(**overrides: object) -> ExecutionDecision:
    strategy_decision = overrides.pop("strategy_reference", None) or _strategy_decision()
    assert isinstance(strategy_decision, StrategyDecision)
    defaults: dict[str, object] = {
        "timestamp": strategy_decision.timestamp,
        "symbol": strategy_decision.symbol,
        "approved": True,
        "approved_allocation": strategy_decision.allocation,
        "decision_type": DecisionType.APPROVED,
        "risk_adjustments": (),
        "reasoning": "Approved at full size; no limits binding.",
        "strategy_reference": strategy_decision,
        "metadata": {},
    }
    defaults.update(overrides)
    return ExecutionDecision(**defaults)  # type: ignore[arg-type]


def _intent(**overrides: object) -> OrderIntent:
    execution_decision = overrides.pop("execution_reference", None) or _execution_decision()
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
    def test_order_intent_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(OrderIntent)}
        assert field_names == {
            "timestamp",
            "symbol",
            "side",
            "quantity",
            "order_type",
            "limit_price",
            "time_in_force",
            "reference_price",
            "stop_loss",
            "take_profit",
            "idempotency_key",
            "reasoning",
            "execution_reference",
            "metadata",
        }


class TestSerializationRoundTrip:
    def test_buy_intent_round_trips_through_dict(self) -> None:
        intent = _intent(metadata={"note": "value"})
        assert OrderIntent.from_dict(intent.to_dict()) == intent

    def test_sell_intent_round_trips_through_dict(self) -> None:
        sell_decision = _execution_decision(
            strategy_reference=_strategy_decision(allocation=0.0),
            approved_allocation=0.0,
        )
        intent = _intent(
            execution_reference=sell_decision,
            side=OrderSide.SELL,
            stop_loss=None,
            take_profit=None,
        )
        assert OrderIntent.from_dict(intent.to_dict()) == intent

    def test_limit_order_round_trips_through_dict(self) -> None:
        intent = _intent(order_type=OrderType.LIMIT, limit_price=99.0)
        assert OrderIntent.from_dict(intent.to_dict()) == intent

    def test_to_dict_is_json_serializable(self) -> None:
        json.dumps(_intent().to_dict())


class TestBackwardCompatibility:
    def test_construction_tolerates_unknown_metadata_keys(self) -> None:
        # OrderIntent.metadata ships with zero guaranteed keys by design
        # (no implementation existed at freeze time) -- any key must be
        # accepted.
        _intent(metadata={"anything": "goes", "here": 123})


class TestInvariantsEnforcedAtTypeLevel:
    """The invariants ADR-012 explicitly enforces at construction, not
    just documents: every field type is first-party (never an Alpaca SDK
    type -- see the import list above, which never imports `alpaca`),
    `stop_loss` is mandatory for a `BUY` and forbidden for a `SELL`, and
    an `OrderIntent` can never be built from a rejected `ExecutionDecision`.
    """

    def test_execution_reference_must_be_approved(self) -> None:
        rejected = _execution_decision(
            approved=False,
            approved_allocation=0.0,
            decision_type=DecisionType.REJECTED,
            risk_adjustments=("x",),
            reasoning="Rejected: x",
        )
        with pytest.raises(ValueError, match="approved"):
            _intent(execution_reference=rejected, side=OrderSide.SELL, stop_loss=None)

    def test_buy_requires_stop_loss(self) -> None:
        with pytest.raises(ValueError, match="stop_loss"):
            _intent(side=OrderSide.BUY, stop_loss=None)

    def test_sell_forbids_stop_loss(self) -> None:
        with pytest.raises(ValueError, match="stop_loss"):
            _intent(side=OrderSide.SELL, stop_loss=95.0)

    def test_quantity_must_be_at_least_one(self) -> None:
        with pytest.raises(ValueError, match="quantity"):
            _intent(quantity=0)

    def test_symbol_and_timestamp_must_match_execution_reference(self) -> None:
        with pytest.raises(ValueError, match="symbol"):
            _intent(symbol="OTHER")
