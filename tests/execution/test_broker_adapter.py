"""Tests for `execution.broker_adapter.AlpacaBrokerAdapter` -- the only
module under `src/execution` that talks to `alpaca-py`. `TradingClient`
is mocked throughout; nothing here makes a real network call."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from alpaca.common.exceptions import APIError
from alpaca.trading.enums import OrderClass

from execution.broker_adapter import AlpacaBrokerAdapter
from execution.models import OrderIntent, OrderSide, OrderType, TimeInForce
from risk.models import ExecutionDecision
from tests.execution.conftest import make_execution_decision


def _intent(
    execution_decision: ExecutionDecision,
    *,
    side: OrderSide = OrderSide.BUY,
    stop_loss: float | None = 95.0,
    take_profit: float | None = None,
) -> OrderIntent:
    return OrderIntent(
        timestamp=execution_decision.timestamp,
        symbol=execution_decision.symbol,
        side=side,
        quantity=10,
        order_type=OrderType.MARKET,
        limit_price=None,
        time_in_force=TimeInForce.DAY,
        reference_price=100.0,
        stop_loss=stop_loss,
        take_profit=take_profit,
        idempotency_key="key-1",
        reasoning="test reasoning",
        execution_reference=execution_decision,
        metadata={},
    )


class TestSubmitOrderSuccess:
    def test_buy_with_only_stop_loss_uses_oto(self) -> None:
        client = MagicMock()
        client.submit_order.return_value = MagicMock(id="broker-order-1")
        adapter = AlpacaBrokerAdapter(client)
        intent = _intent(make_execution_decision(), stop_loss=95.0, take_profit=None)

        result = adapter.submit_order(intent)

        assert result.submitted is True
        assert result.broker_order_id == "broker-order-1"
        request = client.submit_order.call_args.kwargs["order_data"]
        assert request.order_class is OrderClass.OTO
        assert request.qty == 10
        assert request.client_order_id == "key-1"

    def test_buy_with_take_profit_uses_bracket(self) -> None:
        client = MagicMock()
        client.submit_order.return_value = MagicMock(id="broker-order-2")
        adapter = AlpacaBrokerAdapter(client)
        intent = _intent(make_execution_decision(), stop_loss=95.0, take_profit=110.0)

        adapter.submit_order(intent)

        request = client.submit_order.call_args.kwargs["order_data"]
        assert request.order_class is OrderClass.BRACKET

    def test_sell_has_no_order_class(self) -> None:
        client = MagicMock()
        client.submit_order.return_value = MagicMock(id="broker-order-3")
        adapter = AlpacaBrokerAdapter(client)
        decision = make_execution_decision(approved_allocation=0.0, strategy_allocation=0.0)
        intent = _intent(decision, side=OrderSide.SELL, stop_loss=None, take_profit=None)

        adapter.submit_order(intent)

        request = client.submit_order.call_args.kwargs["order_data"]
        assert request.order_class is None
        assert request.stop_loss is None
        assert request.take_profit is None


class TestSubmitOrderFailure:
    def test_api_error_is_caught_and_returned_as_result(self) -> None:
        client = MagicMock()
        client.submit_order.side_effect = APIError("insufficient buying power")
        adapter = AlpacaBrokerAdapter(client)
        intent = _intent(make_execution_decision())

        result = adapter.submit_order(intent)

        assert result.submitted is False
        assert result.error is not None
        assert "insufficient buying power" in result.error


class TestLimitOrderNotImplemented:
    def test_limit_order_raises_not_implemented(self) -> None:
        client = MagicMock()
        adapter = AlpacaBrokerAdapter(client)
        decision = make_execution_decision()
        intent = OrderIntent(
            timestamp=decision.timestamp,
            symbol=decision.symbol,
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            limit_price=99.0,
            time_in_force=TimeInForce.DAY,
            reference_price=100.0,
            stop_loss=95.0,
            take_profit=None,
            idempotency_key="key-limit",
            reasoning="test reasoning",
            execution_reference=decision,
            metadata={},
        )

        with pytest.raises(NotImplementedError):
            adapter.submit_order(intent)


class TestCancelOrder:
    def test_success(self) -> None:
        client = MagicMock()
        adapter = AlpacaBrokerAdapter(client)
        assert adapter.cancel_order("broker-order-1") is True
        client.cancel_order_by_id.assert_called_once_with("broker-order-1")

    def test_api_error_returns_false(self) -> None:
        client = MagicMock()
        client.cancel_order_by_id.side_effect = APIError("not found")
        adapter = AlpacaBrokerAdapter(client)
        assert adapter.cancel_order("missing-order") is False
