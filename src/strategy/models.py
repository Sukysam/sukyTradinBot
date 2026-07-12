"""`StrategyDecision` -- the single contract `strategy.service.
StrategyService.decide` returns, and the only thing about this package
any downstream consumer (Risk Management, Execution, Adaptive Learning,
Signal Orchestration) is meant to depend on. Frozen per
docs/engineering-handbook/Architecture/ADR/ADR-008-StrategyDecision-Contract.md
*before* this package existed at all; full detail in
"docs/engineering-handbook/Standards/StrategyDecision Contract.md".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from common.time import require_utc


@dataclass(frozen=True)
class StrategyDecision:
    """One symbol's investment opinion as of one point in time -- intent,
    not an order. `allocation` is bounded to `[0.0, 1.0]`, never negative:
    this is [00_MASTER_CHARTER.md](../../docs/engineering-handbook/00_MASTER_CHARTER.md)
    invariant #5 ("every strategy is long-only") enforced at construction,
    not left to a call site to remember. `reasoning` must be non-empty,
    extending invariant #6's "never submit an order with no
    reconstructable rationale" one step upstream of the order itself.
    `expected_holding_period` is this strategy's own estimate, not a hard
    exit rule -- see the Standards doc for why it exists (Adaptive
    Learning) and a principled default derivable from
    `RegimeState.transition_probability`.
    """

    timestamp: datetime
    symbol: str
    strategy_id: str
    regime_id: int
    allocation: float
    confidence: float
    expected_holding_period: timedelta
    reasoning: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if self.regime_id < 0:
            raise ValueError(f"regime_id must be >= 0, got {self.regime_id}")
        if not 0.0 <= self.allocation <= 1.0:
            raise ValueError(f"allocation must be in [0.0, 1.0], got {self.allocation}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.expected_holding_period <= timedelta(0):
            raise ValueError(
                f"expected_holding_period must be positive, got {self.expected_holding_period}"
            )
        if not self.reasoning.strip():
            raise ValueError("reasoning must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "regime_id": self.regime_id,
            "allocation": self.allocation,
            "confidence": self.confidence,
            "expected_holding_period_seconds": self.expected_holding_period.total_seconds(),
            "reasoning": self.reasoning,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StrategyDecision:
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            symbol=data["symbol"],
            strategy_id=data["strategy_id"],
            regime_id=data["regime_id"],
            allocation=data["allocation"],
            confidence=data["confidence"],
            expected_holding_period=timedelta(seconds=data["expected_holding_period_seconds"]),
            reasoning=data["reasoning"],
            metadata=dict(data["metadata"]),
        )


__all__ = ["StrategyDecision"]
