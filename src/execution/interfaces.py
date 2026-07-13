"""Protocol interfaces for the Execution Layer's pluggable stages: market
observation, feature observation, stop-loss sizing, and broker
submission. `execution.execution_service.ExecutionService` composes
implementations of the first three; a `BrokerAdapter` is used by whatever
process actually submits an `OrderIntent`, kept separate from
`ExecutionService` itself (see ADR-013) so `ExecutionService` never needs
to know a broker exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from execution.models import ExecutionContext, FeatureSnapshot, OrderIntent

if TYPE_CHECKING:
    from execution.broker_adapter import BrokerSubmissionResult


class MarketSnapshotProvider(Protocol):
    """Supplies a fresh `ExecutionContext` for one symbol, at call time --
    never cached across calls, since `OrderIntent.reference_price` must
    reflect the freshest executable price (see ADR-012's "execution
    contracts describe trading intent, not market observations" note).
    """

    def get_snapshot(self, symbol: str) -> ExecutionContext: ...


class FeatureSnapshotProvider(Protocol):
    """Supplies the minimal `FeatureSnapshot` a `StopLossPolicy` needs
    for one symbol. Deliberately narrower than a full `FeatureVector`
    lookup -- see `FeatureSnapshot`'s own docstring."""

    def get_latest(self, symbol: str) -> FeatureSnapshot: ...


class StopLossPolicy(Protocol):
    """Computes a stop-loss price for a `BUY` order. Never called for a
    `SELL` -- `OrderBuilder` only consults this when routing determines
    an entry/add. Swapping the policy (ATR-based, fixed-percent, a future
    asset-class-specific one) never requires changing `OrderBuilder`
    itself -- see ADR-013 for why this is its own component rather than
    inline logic in the builder.
    """

    @property
    def name(self) -> str: ...

    def compute_stop_loss(
        self,
        context: ExecutionContext,
        feature_snapshot: FeatureSnapshot,
    ) -> float: ...


class BrokerAdapter(Protocol):
    """Translates an `OrderIntent` into a real broker API call. The
    *only* kind of object under `src/execution` allowed to know a
    specific broker (e.g. Alpaca) exists -- `execution_service.py`,
    `order_builder.py`, `router.py`, and every `StopLossPolicy`/
    `*SnapshotProvider` implementation are broker-agnostic by
    construction, never importing this Protocol's concrete
    implementations.
    """

    def submit_order(self, intent: OrderIntent) -> BrokerSubmissionResult: ...

    def cancel_order(self, broker_order_id: str) -> bool: ...


__all__ = [
    "BrokerAdapter",
    "FeatureSnapshotProvider",
    "MarketSnapshotProvider",
    "StopLossPolicy",
]
