"""`FinalDecision` and `SignalInput` -- the contracts `orchestration.
arbitration.arbitrate` (and, later, `orchestration.service`) are built
against. Frozen per
docs/engineering-handbook/Architecture/ADR/ADR-020-FinalDecision-Contract.md
*before* this package existed at all; full detail in
"docs/engineering-handbook/Standards/FinalDecision Contract.md".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from common.time import require_utc


class ArbitrationOutcome(str, Enum):
    """Explicit tri-state classification of a `FinalDecision`, mirroring
    `risk.models.DecisionType`'s role: downstream code branches on
    `decision.outcome is ArbitrationOutcome.SUPPRESSED` rather than
    reconstructing that classification from `primary_allocation`/
    `final_allocation` at every call site. Cross-checked against those
    fields at construction -- see `FinalDecision.__post_init__`.
    """

    CONFIRMED = "confirmed"
    ADJUSTED = "adjusted"
    SUPPRESSED = "suppressed"


@dataclass(frozen=True)
class SignalInput:
    """One advisory source's contribution to a `FinalDecision`. Always
    present on a `FinalDecision` even when that source had nothing to
    contribute -- `considered=False` in that case, never omitted."""

    source: str
    considered: bool
    agrees: bool
    weight: float

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("source must not be empty")
        if not self.considered and self.agrees:
            raise ValueError("agrees must be False when considered is False")
        if not self.considered and self.weight != 0.0:
            raise ValueError(f"weight must be 0.0 when considered is False, got {self.weight}")
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"weight must be in [0.0, 1.0], got {self.weight}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "considered": self.considered,
            "agrees": self.agrees,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SignalInput:
        return cls(
            source=data["source"],
            considered=data["considered"],
            agrees=data["agrees"],
            weight=data["weight"],
        )


@dataclass(frozen=True)
class FinalDecision:
    """The Signal Orchestrator's arbitration of one `StrategyDecision`
    (primary) against advisory `LearningDecision`/`NewsSignal` input.
    `final_allocation` is bounded to `[0.0, primary_allocation]` --
    [00_MASTER_CHARTER.md](../../docs/engineering-handbook/00_MASTER_CHARTER.md)
    invariant #5 one layer downstream of `StrategyDecision.allocation`,
    mirroring `ExecutionDecision.approved_allocation`'s bound: an
    advisory signal may reduce or suppress conviction, never manufacture
    more of it than the Strategy Engine itself proposed. `rationale` must
    be non-empty, extending the same "never produce an unexplained
    decision" principle every prior decision-shaped contract in this
    handbook already carries.
    """

    timestamp: datetime
    symbol: str
    strategy_id: str
    regime_id: int
    primary_allocation: float
    final_allocation: float
    confidence: float
    outcome: ArbitrationOutcome
    learner_input: SignalInput
    news_input: SignalInput
    rationale: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if self.regime_id < 0:
            raise ValueError(f"regime_id must be >= 0, got {self.regime_id}")
        if not 0.0 <= self.primary_allocation <= 1.0:
            raise ValueError(
                f"primary_allocation must be in [0.0, 1.0], got {self.primary_allocation}"
            )
        if not 0.0 <= self.final_allocation <= self.primary_allocation:
            raise ValueError(
                f"final_allocation must be in [0.0, {self.primary_allocation}], "
                f"got {self.final_allocation}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if not self.rationale.strip():
            raise ValueError("rationale must not be empty")
        self._require_consistent_outcome()

    def _require_consistent_outcome(self) -> None:
        if self.final_allocation == self.primary_allocation:
            expected = ArbitrationOutcome.CONFIRMED
        elif self.final_allocation == 0.0 and self.primary_allocation > 0.0:
            expected = ArbitrationOutcome.SUPPRESSED
        else:
            expected = ArbitrationOutcome.ADJUSTED
        if self.outcome is not expected:
            raise ValueError(
                f"outcome {self.outcome!r} is inconsistent with "
                f"primary_allocation={self.primary_allocation!r}, "
                f"final_allocation={self.final_allocation!r} (expected {expected!r})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "regime_id": self.regime_id,
            "primary_allocation": self.primary_allocation,
            "final_allocation": self.final_allocation,
            "confidence": self.confidence,
            "outcome": self.outcome.value,
            "learner_input": self.learner_input.to_dict(),
            "news_input": self.news_input.to_dict(),
            "rationale": self.rationale,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FinalDecision:
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            symbol=data["symbol"],
            strategy_id=data["strategy_id"],
            regime_id=data["regime_id"],
            primary_allocation=data["primary_allocation"],
            final_allocation=data["final_allocation"],
            confidence=data["confidence"],
            outcome=ArbitrationOutcome(data["outcome"]),
            learner_input=SignalInput.from_dict(data["learner_input"]),
            news_input=SignalInput.from_dict(data["news_input"]),
            rationale=data["rationale"],
            metadata=dict(data["metadata"]),
        )


__all__ = ["ArbitrationOutcome", "FinalDecision", "SignalInput"]
