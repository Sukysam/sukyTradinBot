"""Tests for `execution.retry.submit_with_retry`."""

from __future__ import annotations

from unittest.mock import MagicMock

from common.retry import RetryPolicy
from execution.broker_adapter import BrokerSubmissionResult
from execution.models import OrderIntent, OrderSide, OrderType, TimeInForce
from execution.retry import submit_with_retry
from tests.execution.conftest import make_execution_decision

_NO_SLEEP_POLICY = RetryPolicy(max_attempts=3, initial_delay_seconds=0.0, backoff_multiplier=1.0)


def _intent() -> OrderIntent:
    decision = make_execution_decision()
    return OrderIntent(
        timestamp=decision.timestamp,
        symbol=decision.symbol,
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.MARKET,
        limit_price=None,
        time_in_force=TimeInForce.DAY,
        reference_price=100.0,
        stop_loss=95.0,
        take_profit=None,
        idempotency_key="key-1",
        reasoning="test reasoning",
        execution_reference=decision,
        metadata={},
    )


class TestSubmitWithRetry:
    def test_succeeds_on_first_attempt_without_retrying(self) -> None:
        adapter = MagicMock()
        adapter.submit_order.return_value = BrokerSubmissionResult(
            submitted=True, broker_order_id="order-1"
        )
        result = submit_with_retry(adapter, _intent(), policy=_NO_SLEEP_POLICY)
        assert result.submitted is True
        assert adapter.submit_order.call_count == 1

    def test_retries_on_failure_then_succeeds(self) -> None:
        adapter = MagicMock()
        adapter.submit_order.side_effect = [
            BrokerSubmissionResult(submitted=False, error="transient"),
            BrokerSubmissionResult(submitted=True, broker_order_id="order-2"),
        ]
        result = submit_with_retry(adapter, _intent(), policy=_NO_SLEEP_POLICY)
        assert result.submitted is True
        assert result.broker_order_id == "order-2"
        assert adapter.submit_order.call_count == 2

    def test_exhausts_retries_and_returns_failed_result(self) -> None:
        adapter = MagicMock()
        adapter.submit_order.return_value = BrokerSubmissionResult(
            submitted=False, error="persistent failure"
        )
        result = submit_with_retry(adapter, _intent(), policy=_NO_SLEEP_POLICY)
        assert result.submitted is False
        assert adapter.submit_order.call_count == _NO_SLEEP_POLICY.max_attempts

    def test_every_attempt_uses_the_same_idempotency_key(self) -> None:
        adapter = MagicMock()
        adapter.submit_order.return_value = BrokerSubmissionResult(submitted=False, error="x")
        intent = _intent()
        submit_with_retry(adapter, intent, policy=_NO_SLEEP_POLICY)
        submitted_keys = {
            call.args[0].idempotency_key for call in adapter.submit_order.call_args_list
        }
        assert submitted_keys == {intent.idempotency_key}
