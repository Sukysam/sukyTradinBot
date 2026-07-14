"""Protocol interface for Phase B's one pluggable stage: the arbitration
algorithm itself. ADR-020 deliberately leaves this unfrozen -- this
Protocol is what makes `orchestration.policies`' four implementations
swappable without touching `orchestration.arbitration`, the same
"freeze interfaces, not implementation" split every prior milestone's
own policy/strategy layer has used (`strategy.interfaces.Strategy`,
`memory.interfaces.LearningPolicy`, `nlp.interfaces.SentimentScorer`).
"""

from __future__ import annotations

from typing import Protocol

from memory.models import LearningDecision
from nlp.models import NewsSignal
from orchestration.models import FinalDecision
from strategy.models import StrategyDecision


class ArbitrationPolicy(Protocol):
    """Arbitrates one `StrategyDecision` (primary) against optional
    advisory `LearningDecision`/`NewsSignal` input, producing a
    `FinalDecision`. Every implementation must respect `FinalDecision`'s
    own construction-time invariants (`final_allocation` bounded to
    `[0.0, primary_allocation]`, `outcome` consistent with the
    allocations) -- those are enforced by `FinalDecision.__post_init__`
    itself, not something an implementation can bypass."""

    def arbitrate(
        self,
        strategy_decision: StrategyDecision,
        learning_decision: LearningDecision | None,
        news_signal: NewsSignal | None,
    ) -> FinalDecision: ...


__all__ = ["ArbitrationPolicy"]
