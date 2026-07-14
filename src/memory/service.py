"""`MemoryService` -- Phase B's orchestration layer, wiring an
`ExperienceStore` and a `LearningPolicy` together. This is the sanctioned
entry point for anything outside this package that wants to record
experience or ask for a shadow recommendation; see the Standards doc's
shadow-mode guarantee for why `recommend`'s return value is never wired
into `strategy`, `risk`, or `execution`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from random import Random

from memory.interfaces import ExperienceStore, LearningPolicy
from memory.models import ExperienceRecord, LearningDecision


@dataclass
class MemoryService:
    store: ExperienceStore
    policy: LearningPolicy

    def record_experience(self, record: ExperienceRecord) -> None:
        """Append to the Experience Store, then fold the outcome into
        the policy -- in that order, so a policy update never happens
        for an experience that failed to persist."""
        self.store.append(record)
        self.policy.update(record)

    def recommend(
        self,
        *,
        timestamp: datetime,
        symbol: str,
        strategy_id: str,
        regime_id: int,
        production_allocation: float,
        rng: Random,
    ) -> LearningDecision:
        """The learner's shadow opinion for this context. The caller is
        responsible for recording it (see `memory.evaluation`) -- this
        method never itself constructs or influences a real decision."""
        return self.policy.recommend(
            timestamp=timestamp,
            symbol=symbol,
            strategy_id=strategy_id,
            regime_id=regime_id,
            production_allocation=production_allocation,
            rng=rng,
        )


__all__ = ["MemoryService"]
