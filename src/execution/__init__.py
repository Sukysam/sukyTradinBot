"""Execution Layer (Milestone 7).

Converts an `ExecutionDecision` (plus current `PortfolioState`) into a
broker-agnostic `OrderIntent` -- not itself an order submitted to any
broker. Nothing under this package except `broker_adapter.py` may import
an Alpaca SDK type. See
docs/engineering-handbook/Architecture/ADR/ADR-012-OrderIntent-Contract.md
and
docs/engineering-handbook/Architecture/ADR/ADR-013-Execution-Layer-Design.md.

`ExecutionService` is the sanctioned entry point for building an
`OrderIntent`; `execution.retry.submit_with_retry` (given a
`BrokerAdapter`) is the sanctioned entry point for submitting one.
"""

from __future__ import annotations

from execution.config import ExecutionServiceConfig
from execution.exceptions import ExecutionError, TransientBrokerError
from execution.execution_service import ExecutionService
from execution.interfaces import (
    BrokerAdapter,
    FeatureSnapshotProvider,
    MarketSnapshotProvider,
    StopLossPolicy,
)
from execution.models import (
    ExecutionContext,
    FeatureSnapshot,
    OrderIntent,
    OrderSide,
    OrderType,
    TimeInForce,
)
from execution.order_builder import OrderBuilder

__version__ = "0.1.0"

__all__ = [
    "BrokerAdapter",
    "ExecutionContext",
    "ExecutionError",
    "ExecutionService",
    "ExecutionServiceConfig",
    "FeatureSnapshot",
    "FeatureSnapshotProvider",
    "MarketSnapshotProvider",
    "OrderBuilder",
    "OrderIntent",
    "OrderSide",
    "OrderType",
    "StopLossPolicy",
    "TimeInForce",
    "TransientBrokerError",
    "__version__",
]
