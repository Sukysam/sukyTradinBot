"""OCO bracket order construction and submission (Spec Sec. 1, 5, 6).

Every strategy in this system is long-only, so `submit_entry_order` always
issues a BUY. Two structural constraints from Alpaca's live trading API --
neither of which the alpaca-py request models enforce client-side, confirmed
by direct inspection -- are validated here before submission rather than
left to fail server-side:

1. Bracket/OTO orders must use whole-share `qty`; Alpaca does not accept
   fractional/notional sizing on an order with attached stop-loss/take-profit
   legs. `size_to_shares` truncates a target notional to whole shares.
2. A stop-loss leg is mandatory in this system (Spec Sec. 5's 1%-max-risk
   rule assumes a defined stop), so every entry is at least an OTO order.
   `take_profit_price` is optional and upgrades the order to a full
   OCO/BRACKET -- Spec Sec. 3 defines stop levels per volatility tier but
   never a take-profit target, so that price must come from the strategy
   layer that decided to enter; it is never invented here.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.models import Order
from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

logger = logging.getLogger(__name__)


def size_to_shares(notional_value: float, entry_price: float) -> int:
    """Whole-share quantity for a target notional at a given price, truncated
    down -- Alpaca rejects fractional qty on bracket/OTO orders."""
    if entry_price <= 0:
        raise ValueError(f"entry_price must be positive, got {entry_price}")
    return math.floor(notional_value / entry_price)


@dataclass(frozen=True)
class OrderResult:
    submitted: bool
    order: Order | None = None
    error: str | None = None


class OrderExecutor:
    """Thin wrapper over an injected `TradingClient`. Does not construct its
    own client or read credentials -- that is `alpaca_client.py`'s job (not
    yet built); this module only builds and submits order requests and
    surfaces the result.
    """

    def __init__(self, trading_client: TradingClient):
        self.client = trading_client

    def submit_entry_order(
        self,
        ticker: str,
        notional_value: float,
        entry_price: float,
        stop_price: float,
        take_profit_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        client_order_id: str | None = None,
    ) -> OrderResult:
        """Submit a long entry with an attached stop-loss and, if
        `take_profit_price` is given, a take-profit leg too (full OCO
        bracket).
        """
        qty = size_to_shares(notional_value, entry_price)
        if qty < 1:
            return OrderResult(
                submitted=False,
                error=f"Notional {notional_value} at price {entry_price} rounds to 0 whole shares for {ticker}",
            )
        if stop_price >= entry_price:
            return OrderResult(
                submitted=False,
                error=f"stop_price {stop_price} must be below entry_price {entry_price} for a long position",
            )
        if take_profit_price is not None and take_profit_price <= entry_price:
            return OrderResult(
                submitted=False,
                error=f"take_profit_price {take_profit_price} must be above entry_price {entry_price} for a long position",
            )

        order_class = OrderClass.BRACKET if take_profit_price is not None else OrderClass.OTO
        request = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=time_in_force,
            order_class=order_class,
            stop_loss=StopLossRequest(stop_price=stop_price),
            take_profit=TakeProfitRequest(limit_price=take_profit_price) if take_profit_price is not None else None,
            client_order_id=client_order_id or f"regime-trader-{uuid.uuid4()}",
        )

        try:
            order = self.client.submit_order(order_data=request)
        except APIError as exc:
            logger.error("Order submission failed for %s: %s", ticker, exc)
            return OrderResult(submitted=False, error=str(exc))

        logger.info(
            "Submitted %s order for %s: qty=%d stop=%.2f take_profit=%s",
            order_class.value, ticker, qty, stop_price, take_profit_price,
        )
        return OrderResult(submitted=True, order=order if isinstance(order, Order) else None)

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.client.cancel_order_by_id(order_id)
            return True
        except APIError as exc:
            logger.error("Cancel failed for order %s: %s", order_id, exc)
            return False

    def liquidate_position(self, ticker: str) -> OrderResult:
        """Market-close a single position. Distinct from
        `liquidate_all_positions` below: this is for a per-symbol reaction
        (e.g. a correlation or concentration issue resolved by exiting one
        name), not an account-wide circuit-breaker halt.
        """
        try:
            order = self.client.close_position(ticker)
        except APIError as exc:
            logger.error("Liquidation failed for %s: %s", ticker, exc)
            return OrderResult(submitted=False, error=str(exc))
        logger.warning("Liquidated position: %s", ticker)
        return OrderResult(submitted=True, order=order if isinstance(order, Order) else None)

    def liquidate_all_positions(self, cancel_open_orders: bool = True) -> bool:
        """Closes every open position -- the action side of
        `risk_manager.CircuitBreakerDecision.liquidate=True` for the daily,
        weekly, and emergency halts (Spec Sec. 5).
        """
        try:
            self.client.close_all_positions(cancel_orders=cancel_open_orders)
        except APIError as exc:
            logger.critical("Liquidate-all failed: %s", exc)
            return False
        logger.critical("All positions liquidated (circuit breaker).")
        return True
