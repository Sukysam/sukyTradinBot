"""`OrderBuilder` -- combines routing (buy/sell/hold), a `StopLossPolicy`,
and the transient `ExecutionContext`/`FeatureSnapshot` observations into
one `OrderIntent`, or `None` when no order is needed.

Deliberately thin: this module owns no pricing or stop-sizing logic of
its own, only orchestration -- see ADR-013 for why `router.py` and
`StopLossPolicy` are kept as separate, independently testable components
rather than inline here.
"""

from __future__ import annotations

from dataclasses import dataclass

from execution.interfaces import StopLossPolicy
from execution.models import (
    ExecutionContext,
    FeatureSnapshot,
    OrderIntent,
    OrderSide,
    OrderType,
    TimeInForce,
)
from execution.router import route
from risk.models import ExecutionDecision, PortfolioState


@dataclass(frozen=True)
class OrderBuilder:
    stop_loss_policy: StopLossPolicy
    time_in_force: TimeInForce = TimeInForce.DAY

    def build(
        self,
        execution_decision: ExecutionDecision,
        portfolio: PortfolioState,
        context: ExecutionContext,
        feature_snapshot: FeatureSnapshot,
    ) -> OrderIntent | None:
        if context.symbol != execution_decision.symbol:
            raise ValueError(
                f"context.symbol {context.symbol!r} does not match "
                f"execution_decision.symbol {execution_decision.symbol!r}"
            )
        if feature_snapshot.symbol != execution_decision.symbol:
            raise ValueError(
                f"feature_snapshot.symbol {feature_snapshot.symbol!r} does not match "
                f"execution_decision.symbol {execution_decision.symbol!r}"
            )

        routing = route(execution_decision, portfolio, context.reference_price)
        if routing is None:
            return None

        if routing.side is OrderSide.BUY:
            stop_loss = self.stop_loss_policy.compute_stop_loss(context, feature_snapshot)
            if stop_loss >= context.reference_price:
                # A degenerate ATR reading (e.g. zero recent range) can
                # produce a non-protective stop -- fail loudly rather than
                # submit an entry with no real protection.
                raise ValueError(
                    f"{self.stop_loss_policy.name} produced a non-protective stop_loss "
                    f"{stop_loss} >= reference_price {context.reference_price} for "
                    f"{execution_decision.symbol}"
                )
            take_profit = None
            reasoning = (
                f"Routed BUY {routing.quantity} shares of {execution_decision.symbol} "
                f"toward target allocation {execution_decision.approved_allocation:.4f} "
                f"(strategy {execution_decision.strategy_reference.strategy_id!r}); "
                f"stop_loss={stop_loss:.4f} via {self.stop_loss_policy.name}."
            )
        else:
            stop_loss = None
            take_profit = None
            reasoning = (
                f"Routed SELL {routing.quantity} shares of {execution_decision.symbol} "
                f"toward target allocation {execution_decision.approved_allocation:.4f} "
                f"(strategy {execution_decision.strategy_reference.strategy_id!r})."
            )

        idempotency_key = (
            f"{execution_decision.symbol}-{execution_decision.timestamp.isoformat()}-"
            f"{routing.side.value}-{routing.quantity}-"
            f"{execution_decision.strategy_reference.strategy_id}"
        )

        return OrderIntent(
            timestamp=execution_decision.timestamp,
            symbol=execution_decision.symbol,
            side=routing.side,
            quantity=routing.quantity,
            order_type=OrderType.MARKET,
            limit_price=None,
            time_in_force=self.time_in_force,
            reference_price=context.reference_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            idempotency_key=idempotency_key,
            reasoning=reasoning,
            execution_reference=execution_decision,
            metadata={},
        )


__all__ = ["OrderBuilder"]
