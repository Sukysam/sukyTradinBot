"""Configuration for training, model selection, and normalization.

Per docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md's
"freeze interfaces, not implementation" framing: `RegimeState`, the
`Normalizer` protocol, and `RegimeService`'s public methods are the frozen
surface. Everything in this module -- state count, covariance type,
convergence thresholds, the selection criterion -- is exactly the
opposite: quantitative choices expected to be revisited as the model is
evaluated, so every one of them is a named, explicit, overridable
default, never a hardcoded magic number inside `trainer.py`/`selector.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SelectionCriterion(str, Enum):
    """Which information criterion `selector.py` minimizes over candidate
    state counts. Both are always computed and recorded regardless of
    which one drives selection -- see `models.ModelMetadata`.
    """

    BIC = "bic"
    AIC = "aic"


@dataclass(frozen=True)
class TrainingConfig:
    """Hyperparameters for fitting one candidate state count via
    Baum-Welch/EM. `n_init` independent random restarts are fit and only
    the highest-log-likelihood one is kept -- EM converges to a local
    optimum, so a single unlucky initialization can make a good state
    count look worse than a bad one that happened to initialize well
    (ported from `regime-trader/core/hmm_engine.py`'s
    `fit_with_bic_selection`, which established this exact pattern).
    """

    covariance_type: str = "full"
    n_init: int = 5
    n_iter: int = 200
    tol: float = 1e-4
    random_state: int = 42

    def __post_init__(self) -> None:
        if self.n_init < 1:
            raise ValueError(f"n_init must be >= 1, got {self.n_init}")
        if self.n_iter < 1:
            raise ValueError(f"n_iter must be >= 1, got {self.n_iter}")
        if self.tol <= 0:
            raise ValueError(f"tol must be > 0, got {self.tol}")


@dataclass(frozen=True)
class SelectionConfig:
    """Which candidate state counts `selector.py` fits and compares, and
    which criterion picks the winner among them.
    """

    candidate_states: tuple[int, ...] = (3, 4, 5, 6, 7)
    criterion: SelectionCriterion = SelectionCriterion.BIC

    def __post_init__(self) -> None:
        if not self.candidate_states:
            raise ValueError("candidate_states must not be empty")
        if any(k < 1 for k in self.candidate_states):
            raise ValueError(
                f"every candidate state count must be >= 1, got {self.candidate_states}"
            )


@dataclass(frozen=True)
class HMMConfig:
    """The one config object `RegimeService.train` takes -- bundles
    `TrainingConfig` (how to fit one candidate) and `SelectionConfig`
    (which candidates, which criterion), so a caller overriding either
    doesn't need to know the other exists.
    """

    training: TrainingConfig = field(default_factory=TrainingConfig)
    selection: SelectionConfig = field(default_factory=SelectionConfig)


__all__ = ["HMMConfig", "SelectionConfig", "SelectionCriterion", "TrainingConfig"]
