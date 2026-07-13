"""Reconciles an `ExecutionDecision`'s target allocation against the
current position to decide whether an order is needed at all, and if so,
its side and whole-share quantity.

Neither `StrategyDecision` nor `ExecutionDecision` expresses "buy N
shares" or "sell N shares" -- both work in target allocation *fractions*
of `PortfolioState.equity`, evaluated fresh every cycle with no memory of
what was submitted last cycle. Determining the actual delta against
today's real position is this module's job, not something either
upstream contract does.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from execution.models import OrderSide
from risk.models import ExecutionDecision, PortfolioState

#: Below this notional delta, no order is worth submitting -- avoids
#: dust orders from floating-point noise or an allocation that's already
#: effectively at target.
MIN_ORDER_NOTIONAL = 1.0


@dataclass(frozen=True)
class RoutingDecision:
    side: OrderSide
    quantity: int


def _current_position_value(portfolio: PortfolioState, symbol: str) -> float:
    return sum(p.market_value for p in portfolio.positions if p.ticker == symbol)


def route(
    execution_decision: ExecutionDecision,
    portfolio: PortfolioState,
    reference_price: float,
) -> RoutingDecision | None:
    """Returns `None` when no order is needed -- the target allocation is
    already (approximately) met, or the delta rounds to fewer than one
    whole share. Never returns a zero-quantity `RoutingDecision`.

    A `SELL` quantity is capped at the current position's *approximate*
    share count (`current_position_value / reference_price`) -- `Position.
    market_value` is a dollar mark-to-market figure, not a stored share
    count, the same approximation `core/risk_manager.py`'s own
    `ProposedTrade.dollar_risk` already documents as "an approximation,
    not a guarantee." This never oversells per invariant #5 (long-only:
    a `SELL` only ever exits an existing long, never opens a short), but
    the exact share count sold may differ slightly from a broker's own
    books if `reference_price` has moved since the position was marked.
    """
    if reference_price <= 0:
        raise ValueError(f"reference_price must be > 0, got {reference_price}")

    current_value = _current_position_value(portfolio, execution_decision.symbol)
    target_value = execution_decision.approved_allocation * portfolio.equity
    delta_value = target_value - current_value

    if abs(delta_value) < MIN_ORDER_NOTIONAL:
        return None

    if delta_value > 0:
        quantity = math.floor(delta_value / reference_price)
        if quantity < 1:
            return None
        return RoutingDecision(side=OrderSide.BUY, quantity=quantity)

    quantity = math.floor(abs(delta_value) / reference_price)
    max_sellable = math.floor(current_value / reference_price)
    quantity = min(quantity, max_sellable)
    if quantity < 1:
        return None
    return RoutingDecision(side=OrderSide.SELL, quantity=quantity)


__all__ = ["MIN_ORDER_NOTIONAL", "RoutingDecision", "route"]
