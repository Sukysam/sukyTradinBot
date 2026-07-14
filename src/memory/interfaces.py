"""Protocol interfaces for the Adaptive Learning / Memory Loop's two
pluggable stages: experience persistence and the learning policy. ADR-016
freezes `ExperienceRecord`/`LearningDecision` -- the *outputs* of these
Protocols -- but deliberately leaves how experience is persisted and
which algorithm computes a recommendation as implementation detail. These
Protocols are what make both swappable without touching `service.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from random import Random
from typing import Protocol

from memory.models import ExperienceRecord, LearningDecision


class ExperienceStore(Protocol):
    """An append-only log of closed-trade outcomes. No method on this
    Protocol permits mutating or deleting a record once appended -- the
    Experience Store is an immutable historical log by construction, not
    just by convention."""

    def append(self, record: ExperienceRecord) -> None: ...

    def for_context(self, *, strategy_id: str, regime_id: int) -> Sequence[ExperienceRecord]:
        """Every `ExperienceRecord` appended for this `(strategy_id,
        regime_id)` context, in append order."""
        ...

    def __len__(self) -> int: ...


class LearningPolicy(Protocol):
    """Learns from `ExperienceRecord`s and produces `LearningDecision`
    shadow recommendations. Never itself constructs an `OrderIntent`,
    `ExecutionDecision`, or `StrategyDecision` -- see the Standards doc's
    shadow-mode guarantee."""

    def update(self, record: ExperienceRecord) -> None:
        """Incorporate one closed trade's outcome into this policy's
        state for its `(strategy_id, regime_id)` context."""
        ...

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
        """The learner's shadow opinion for this context, given a
        caller-supplied `rng` for deterministic, reproducible sampling --
        never `random.random()`/module-level global state, matching this
        codebase's "explicit over implicit" dependency-injection
        convention for anything non-deterministic."""
        ...


__all__ = ["ExperienceStore", "LearningPolicy"]
