"""`OrchestrationConfig` -- tunables for `orchestration.arbitration.
arbitrate`. Deliberately not frozen as a contract (ADR-020 only freezes
the *outputs*, `FinalDecision`/`SignalInput`) -- this shape can evolve
freely, including once Phase B's pluggable policies replace Phase A's
single deterministic rule.
"""

from __future__ import annotations

from dataclasses import dataclass

#: A `LearningDecision.recommended_allocation` within this distance of
#: `StrategyDecision.allocation` counts as agreement -- matches
#: `memory.evaluation.DEFAULT_AGREEMENT_TOLERANCE`, kept identical rather
#: than re-derived differently here.
DEFAULT_AGREEMENT_TOLERANCE = 0.05

#: Fraction `final_allocation` is cut by when exactly one advisory signal
#: disagrees with the primary `StrategyDecision`. Both signals disagreeing
#: suppresses the decision entirely (`final_allocation = 0.0`), regardless
#: of this value.
DEFAULT_DISAGREEMENT_PENALTY = 0.5


@dataclass(frozen=True)
class OrchestrationConfig:
    agreement_tolerance: float = DEFAULT_AGREEMENT_TOLERANCE
    disagreement_penalty: float = DEFAULT_DISAGREEMENT_PENALTY

    def __post_init__(self) -> None:
        if self.agreement_tolerance < 0.0:
            raise ValueError(f"agreement_tolerance must be >= 0, got {self.agreement_tolerance}")
        if not 0.0 < self.disagreement_penalty <= 1.0:
            raise ValueError(
                f"disagreement_penalty must be in (0.0, 1.0], got {self.disagreement_penalty}"
            )


__all__ = [
    "DEFAULT_AGREEMENT_TOLERANCE",
    "DEFAULT_DISAGREEMENT_PENALTY",
    "OrchestrationConfig",
]
