"""`AlpacaBrokerAdapter` -- the *only* module under `src/execution`
allowed to import `alpaca-py`. Translates an `OrderIntent` into a real
Alpaca API call, matching `regime-trader/broker/order_executor.py`'s
existing OTO/BRACKET construction logic, ported to consume `OrderIntent`
instead of raw `entry_price`/`stop_price`/`notional_value` parameters.

Whole-share quantity and the mandatory-stop-for-a-BUY rule -- the two
client-side-unenforced Alpaca constraints `order_executor.py` validates
by hand -- are already guaranteed by `OrderIntent.__post_init__` (ADR-012)
by the time an `OrderIntent` reaches this adapter, so this module doesn't
re-validate them; it only translates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import TimeInForce as AlpacaTimeInForce
from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

from execution.models import OrderIntent, OrderSide, OrderType, TimeInForce

logger = logging.getLogger(__name__)

_SIDE_MAP = {OrderSide.BUY: AlpacaOrderSide.BUY, OrderSide.SELL: AlpacaOrderSide.SELL}
_TIME_IN_FORCE_MAP = {
    TimeInForce.DAY: AlpacaTimeInForce.DAY,
    TimeInForce.GTC: AlpacaTimeInForce.GTC,
}


@dataclass(frozen=True)
class BrokerSubmissionResult:
    submitted: bool
    broker_order_id: str | None = None
    error: str | None = None


class AlpacaBrokerAdapter:
    """Thin wrapper over an injected `TradingClient` -- does not construct
    its own client or read credentials, matching `order_executor.py
    ::OrderExecutor`'s existing pattern (client construction and
    credential handling stay in `main.py`/`alpaca_client.py`).
    """

    def __init__(self, trading_client: TradingClient) -> None:
        self._client = trading_client

    def submit_order(self, intent: OrderIntent) -> BrokerSubmissionResult:
        if intent.order_type is OrderType.LIMIT:
            raise NotImplementedError(
                "OrderType.LIMIT has no broker translation yet -- "
                "Standards/OrderIntent Contract.md documents it as a reserved, "
                "not-yet-implemented value."
            )

        request = MarketOrderRequest(
            symbol=intent.symbol,
            qty=intent.quantity,
            side=_SIDE_MAP[intent.side],
            time_in_force=_TIME_IN_FORCE_MAP[intent.time_in_force],
            order_class=self._order_class(intent),
            stop_loss=(
                StopLossRequest(stop_price=intent.stop_loss)
                if intent.stop_loss is not None
                else None
            ),
            take_profit=(
                TakeProfitRequest(limit_price=intent.take_profit)
                if intent.take_profit is not None
                else None
            ),
            client_order_id=intent.idempotency_key,
        )

        try:
            order = self._client.submit_order(order_data=request)
        except APIError as exc:
            logger.error("Order submission failed for %s: %s", intent.symbol, exc)
            return BrokerSubmissionResult(submitted=False, error=str(exc))

        broker_order_id = str(getattr(order, "id", "")) or None
        logger.info(
            "Submitted %s %s order for %s: qty=%d idempotency_key=%s",
            intent.side.value,
            request.order_class.value if request.order_class else "simple",
            intent.symbol,
            intent.quantity,
            intent.idempotency_key,
        )
        return BrokerSubmissionResult(submitted=True, broker_order_id=broker_order_id)

    def cancel_order(self, broker_order_id: str) -> bool:
        try:
            self._client.cancel_order_by_id(broker_order_id)
            return True
        except APIError as exc:
            logger.error("Cancel failed for order %s: %s", broker_order_id, exc)
            return False

    @staticmethod
    def _order_class(intent: OrderIntent) -> OrderClass | None:
        if intent.side is not OrderSide.BUY:
            return None
        return OrderClass.BRACKET if intent.take_profit is not None else OrderClass.OTO


__all__ = ["AlpacaBrokerAdapter", "BrokerSubmissionResult"]
