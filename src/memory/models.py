"""`ExperienceRecord` and `LearningDecision` -- the two contracts the
Adaptive Learning / Memory Loop (Milestone 9) is built against. Frozen per
docs/engineering-handbook/Architecture/ADR/ADR-016-LearningDecision-Contract.md
*before* this package existed at all; full detail in
"docs/engineering-handbook/Standards/LearningDecision Contract.md".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from common.time import require_utc


@dataclass(frozen=True)
class ExperienceRecord:
    """The atomic unit of the Experience Store -- one closed trade's
    context and realized outcome. Conceptually downstream of
    `backtest.models.TradeRecord` (or, once a live trading loop exists,
    whatever produces the equivalent live outcome), not a replacement
    for it."""

    symbol: str
    strategy_id: str
    regime_id: int
    production_allocation: float
    realized_pnl: float
    realized_pnl_pct: float
    won: bool
    entry_timestamp: datetime
    exit_timestamp: datetime
    holding_period: timedelta
    source_run_id: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_utc(self.entry_timestamp, "entry_timestamp")
        require_utc(self.exit_timestamp, "exit_timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if self.regime_id < 0:
            raise ValueError(f"regime_id must be >= 0, got {self.regime_id}")
        if not 0.0 <= self.production_allocation <= 1.0:
            raise ValueError(
                f"production_allocation must be in [0.0, 1.0], got {self.production_allocation}"
            )
        if self.exit_timestamp <= self.entry_timestamp:
            raise ValueError("exit_timestamp must be after entry_timestamp")
        if self.holding_period != self.exit_timestamp - self.entry_timestamp:
            raise ValueError("holding_period must equal exit_timestamp - entry_timestamp")
        if self.won != (self.realized_pnl > 0.0):
            raise ValueError(
                f"won ({self.won}) must equal realized_pnl > 0.0 (realized_pnl={self.realized_pnl})"
            )
        if not self.source_run_id:
            raise ValueError("source_run_id must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "regime_id": self.regime_id,
            "production_allocation": self.production_allocation,
            "realized_pnl": self.realized_pnl,
            "realized_pnl_pct": self.realized_pnl_pct,
            "won": self.won,
            "entry_timestamp": self.entry_timestamp.isoformat(),
            "exit_timestamp": self.exit_timestamp.isoformat(),
            "holding_period_seconds": self.holding_period.total_seconds(),
            "source_run_id": self.source_run_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExperienceRecord:
        return cls(
            symbol=data["symbol"],
            strategy_id=data["strategy_id"],
            regime_id=data["regime_id"],
            production_allocation=data["production_allocation"],
            realized_pnl=data["realized_pnl"],
            realized_pnl_pct=data["realized_pnl_pct"],
            won=data["won"],
            entry_timestamp=datetime.fromisoformat(data["entry_timestamp"]),
            exit_timestamp=datetime.fromisoformat(data["exit_timestamp"]),
            holding_period=timedelta(seconds=data["holding_period_seconds"]),
            source_run_id=data["source_run_id"],
            metadata=dict(data["metadata"]),
        )


@dataclass(frozen=True)
class LearningDecision:
    """The learner's shadow opinion at the moment a real `StrategyDecision`
    was made for a given `(symbol, strategy_id, regime_id)` -- recorded
    for later comparison, never consumed by `strategy`, `risk`, or
    `execution` in this milestone. See the Standards doc's "shadow-mode
    guarantee" section: that boundary is architectural, not just a
    property of this type."""

    timestamp: datetime
    symbol: str
    strategy_id: str
    regime_id: int
    production_allocation: float
    recommended_allocation: float
    confidence: float
    sample_size: int
    rationale: str
    model_version: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if self.regime_id < 0:
            raise ValueError(f"regime_id must be >= 0, got {self.regime_id}")
        if not 0.0 <= self.production_allocation <= 1.0:
            raise ValueError(
                f"production_allocation must be in [0.0, 1.0], got {self.production_allocation}"
            )
        if not 0.0 <= self.recommended_allocation <= 1.0:
            raise ValueError(
                f"recommended_allocation must be in [0.0, 1.0], got {self.recommended_allocation}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.sample_size < 0:
            raise ValueError(f"sample_size must be >= 0, got {self.sample_size}")
        if not self.rationale.strip():
            raise ValueError("rationale must not be empty")
        if not self.model_version:
            raise ValueError("model_version must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "regime_id": self.regime_id,
            "production_allocation": self.production_allocation,
            "recommended_allocation": self.recommended_allocation,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "rationale": self.rationale,
            "model_version": self.model_version,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LearningDecision:
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            symbol=data["symbol"],
            strategy_id=data["strategy_id"],
            regime_id=data["regime_id"],
            production_allocation=data["production_allocation"],
            recommended_allocation=data["recommended_allocation"],
            confidence=data["confidence"],
            sample_size=data["sample_size"],
            rationale=data["rationale"],
            model_version=data["model_version"],
            metadata=dict(data["metadata"]),
        )


__all__ = ["ExperienceRecord", "LearningDecision"]
