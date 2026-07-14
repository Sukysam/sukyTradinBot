"""`MemoryConfig` -- tunables for `memory.bandit.ThompsonSamplingPolicy`
and `memory.service.MemoryService`. Deliberately not frozen as a contract
(ADR-016 only freezes the *outputs*, `ExperienceRecord`/`LearningDecision`)
-- this shape can evolve freely.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Beta(alpha, beta) prior before any experience is observed -- Beta(1, 1)
#: is the uniform prior, matching the reference bandit design (see
#: docs/engineering-handbook/Architecture/Reinforcement Learning Memory
#: Loop.md).
DEFAULT_PRIOR_ALPHA = 1.0
DEFAULT_PRIOR_BETA = 1.0

#: `confidence = sample_size / (sample_size + CONFIDENCE_SMOOTHING)` --
#: how quickly `LearningDecision.confidence` approaches 1.0 as experience
#: accumulates for a context. Larger values require more samples before
#: a recommendation is reported as confident.
DEFAULT_CONFIDENCE_SMOOTHING = 10.0

#: Identifies the learning-policy version that produced a
#: `LearningDecision` -- see `LearningDecision.model_version`.
DEFAULT_MODEL_VERSION = "thompson-bandit-v1"


@dataclass(frozen=True)
class MemoryConfig:
    prior_alpha: float = DEFAULT_PRIOR_ALPHA
    prior_beta: float = DEFAULT_PRIOR_BETA
    confidence_smoothing: float = DEFAULT_CONFIDENCE_SMOOTHING
    model_version: str = DEFAULT_MODEL_VERSION

    def __post_init__(self) -> None:
        if self.prior_alpha <= 0.0:
            raise ValueError(f"prior_alpha must be > 0, got {self.prior_alpha}")
        if self.prior_beta <= 0.0:
            raise ValueError(f"prior_beta must be > 0, got {self.prior_beta}")
        if self.confidence_smoothing <= 0.0:
            raise ValueError(f"confidence_smoothing must be > 0, got {self.confidence_smoothing}")
        if not self.model_version:
            raise ValueError("model_version must not be empty")


__all__ = [
    "DEFAULT_CONFIDENCE_SMOOTHING",
    "DEFAULT_MODEL_VERSION",
    "DEFAULT_PRIOR_ALPHA",
    "DEFAULT_PRIOR_BETA",
    "MemoryConfig",
]
