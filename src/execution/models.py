"""`OrderIntent` -- the single contract `execution.execution_service.
ExecutionService.decide` returns, and the only thing about this package
any broker adapter is meant to depend on. Frozen per
docs/engineering-handbook/Architecture/ADR/ADR-012-OrderIntent-Contract.md
*before* this package existed at all; full detail in
"docs/engineering-handbook/Standards/OrderIntent Contract.md".

Also defines `ExecutionContext` and `FeatureSnapshot` -- internal,
deliberately *unfrozen* value objects that never leave `src/execution`.
Per ADR-012's amended principle ("execution contracts describe trading
intent, not market observations"), these two carry transient market
observations (a live quote, a fresh ATR reading) gathered at order-build
time; only the resulting `OrderIntent` is a durable, versioned contract.
See ADR-013-Execution-Layer-Design.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from common.time import require_utc
from risk.models import ExecutionDecision


class OrderSide(str, Enum):
    """First-party -- never `alpaca.trading.enums.OrderSide`. `SELL` is
    only ever an exit/reduction of an existing long position, matching
    `OrderExecutor.liquidate_position`'s semantics -- never a new short
    entry, per [00_MASTER_CHARTER.md](../../docs/engineering-handbook/00_MASTER_CHARTER.md)
    invariant #5.
    """

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """First-party -- never `alpaca.trading.enums.OrderType`. Only
    `MARKET` has a real implementation as of Milestone 7; `LIMIT` is a
    reserved value for a future implementation (see `limit_price`)."""

    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(str, Enum):
    """First-party -- never `alpaca.trading.enums.TimeInForce`."""

    DAY = "day"
    GTC = "gtc"


@dataclass(frozen=True)
class OrderIntent:
    """One broker-agnostic order description, built from an approved
    `ExecutionDecision` -- not itself an order submitted to any broker.
    `stop_loss` is mandatory for a `BUY` (every entry carries a
    protective stop, per invariant #5 and
    [03_BACKEND_ENGINEER.md](../../docs/engineering-handbook/03_BACKEND_ENGINEER.md)'s
    existing acceptance criterion) and forbidden for a `SELL` (an exit
    closes risk, it doesn't need its own stop).
    """

    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    limit_price: float | None
    time_in_force: TimeInForce
    reference_price: float
    stop_loss: float | None
    take_profit: float | None
    idempotency_key: str
    reasoning: str
    execution_reference: ExecutionDecision
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.symbol != self.execution_reference.symbol:
            raise ValueError(
                f"symbol {self.symbol!r} does not match "
                f"execution_reference.symbol {self.execution_reference.symbol!r}"
            )
        if self.timestamp != self.execution_reference.timestamp:
            raise ValueError(
                f"timestamp {self.timestamp!r} does not match "
                f"execution_reference.timestamp {self.execution_reference.timestamp!r}"
            )
        if not self.execution_reference.approved:
            raise ValueError("execution_reference.approved must be True")
        if self.quantity < 1:
            raise ValueError(f"quantity must be >= 1, got {self.quantity}")
        if self.reference_price <= 0:
            raise ValueError(f"reference_price must be > 0, got {self.reference_price}")

        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None or self.limit_price <= 0:
                raise ValueError("limit_price must be a positive float when order_type is LIMIT")
        elif self.limit_price is not None:
            raise ValueError("limit_price must be None when order_type is MARKET")

        if self.side is OrderSide.BUY:
            if self.stop_loss is None or self.stop_loss >= self.reference_price:
                raise ValueError(
                    "stop_loss must be a float strictly less than reference_price for a BUY"
                )
            if self.take_profit is not None and self.take_profit <= self.reference_price:
                raise ValueError(
                    "take_profit must be strictly greater than reference_price when set"
                )
        else:
            if self.stop_loss is not None:
                raise ValueError("stop_loss must be None for a SELL")
            if self.take_profit is not None:
                raise ValueError("take_profit must be None for a SELL")

        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        if not self.reasoning.strip():
            raise ValueError("reasoning must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "time_in_force": self.time_in_force.value,
            "reference_price": self.reference_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "idempotency_key": self.idempotency_key,
            "reasoning": self.reasoning,
            "execution_reference": self.execution_reference.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OrderIntent:
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            symbol=data["symbol"],
            side=OrderSide(data["side"]),
            quantity=data["quantity"],
            order_type=OrderType(data["order_type"]),
            limit_price=data["limit_price"],
            time_in_force=TimeInForce(data["time_in_force"]),
            reference_price=data["reference_price"],
            stop_loss=data["stop_loss"],
            take_profit=data["take_profit"],
            idempotency_key=data["idempotency_key"],
            reasoning=data["reasoning"],
            execution_reference=ExecutionDecision.from_dict(data["execution_reference"]),
            metadata=dict(data["metadata"]),
        )


@dataclass(frozen=True)
class ExecutionContext:
    """Transient market observation used to build one `OrderIntent` --
    never frozen as a contract, never serialized alongside an
    `OrderIntent` (only `reference_price` survives into that durable
    record). `bid`/`ask`/`spread` are `None` when the `MarketSnapshotProvider`
    in use can't supply them (e.g. a bar-close-only provider has no real
    quote data) -- an honest gap, not a fabricated value.
    """

    symbol: str
    timestamp: datetime
    reference_price: float
    bid: float | None
    ask: float | None
    spread: float | None
    tick_size: float
    price_source: str

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.reference_price <= 0:
            raise ValueError(f"reference_price must be > 0, got {self.reference_price}")
        if self.tick_size <= 0:
            raise ValueError(f"tick_size must be > 0, got {self.tick_size}")
        if not self.price_source:
            raise ValueError("price_source must not be empty")


@dataclass(frozen=True)
class FeatureSnapshot:
    """The minimal slice of feature data a `StopLossPolicy` needs --
    never a full `FeatureVector`. `Execution only asks for what it
    needs` (see ADR-013): threading the entire `FeatureVector` through
    the execution layer would couple order construction to every
    feature this platform ever adds, most of which have nothing to do
    with sizing a stop.
    """

    symbol: str
    timestamp: datetime
    atr_14: float
    realized_volatility_20: float

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.atr_14 < 0:
            raise ValueError(f"atr_14 must be >= 0, got {self.atr_14}")
        if self.realized_volatility_20 < 0:
            raise ValueError(
                f"realized_volatility_20 must be >= 0, got {self.realized_volatility_20}"
            )


__all__ = [
    "ExecutionContext",
    "FeatureSnapshot",
    "OrderIntent",
    "OrderSide",
    "OrderType",
    "TimeInForce",
]
