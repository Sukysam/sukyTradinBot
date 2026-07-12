"""Model selection: fits every candidate state count in
`SelectionConfig.candidate_states` via `trainer.train`, scores each with
the configured information criterion, and returns whichever minimizes it.

Free-parameter counting (`_n_free_parameters`) is ported from
`regime-trader/core/hmm_engine.py`'s `_n_free_parameters`/`_bic` -- same
formula, extended here with AIC alongside BIC (see
docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md for why
both are always computed and recorded regardless of which one drives
selection).
"""

from __future__ import annotations

import logging

import numpy as np
import numpy.typing as npt

from hmm.config import SelectionConfig, SelectionCriterion, TrainingConfig
from hmm.exceptions import TrainingError
from hmm.models import TrainedModel
from hmm.trainer import train

logger = logging.getLogger(__name__)


def _n_free_parameters(n_components: int, n_features: int) -> int:
    """Free parameter count for a full-covariance GaussianHMM: transition
    matrix (n*(n-1), rows sum to 1), start distribution (n-1, sums to 1),
    means (n*d), and covariances (n * d*(d+1)/2, symmetric matrices).
    """
    transition_params = n_components * (n_components - 1)
    start_prob_params = n_components - 1
    mean_params = n_components * n_features
    cov_params = n_components * n_features * (n_features + 1) // 2
    return transition_params + start_prob_params + mean_params + cov_params


def bic(log_likelihood: float, n_samples: int, n_components: int, n_features: int) -> float:
    k = _n_free_parameters(n_components, n_features)
    return float(-2.0 * log_likelihood + k * np.log(n_samples))


def aic(log_likelihood: float, n_components: int, n_features: int) -> float:
    k = _n_free_parameters(n_components, n_features)
    return -2.0 * log_likelihood + 2.0 * k


class SelectionResult:
    """The winning `TrainedModel` plus both criteria's scores for every
    candidate that fit successfully, so `persistence.py` can record BIC
    and AIC together regardless of which one was actually used to choose.
    """

    def __init__(
        self,
        trained_model: TrainedModel,
        criterion: SelectionCriterion,
        bic_by_candidate: dict[int, float],
        aic_by_candidate: dict[int, float],
    ) -> None:
        self.trained_model = trained_model
        self.criterion = criterion
        self.bic_by_candidate = bic_by_candidate
        self.aic_by_candidate = aic_by_candidate

    @property
    def bic(self) -> float:
        return self.bic_by_candidate[self.trained_model.n_states]

    @property
    def aic(self) -> float:
        return self.aic_by_candidate[self.trained_model.n_states]


def select(
    X: npt.NDArray[np.float64],
    selection_config: SelectionConfig,
    training_config: TrainingConfig,
) -> SelectionResult:
    """Fit every candidate in `selection_config.candidate_states`, compute
    both BIC and AIC for each successful fit, and return the `TrainedModel`
    minimizing `selection_config.criterion`.

    Raises `TrainingError` if every single candidate fails to fit (not
    just every restart of one candidate -- `trainer.train` already raises
    per-candidate in that narrower case, caught and logged here so one bad
    candidate doesn't abort the whole sweep).
    """
    bic_by_candidate: dict[int, float] = {}
    aic_by_candidate: dict[int, float] = {}
    candidates: dict[int, TrainedModel] = {}

    for n_states in selection_config.candidate_states:
        try:
            trained = train(X, n_states, training_config)
        except TrainingError as exc:
            logger.warning("Skipping n_states=%d: %s", n_states, exc)
            continue

        candidates[n_states] = trained
        bic_by_candidate[n_states] = bic(
            trained.log_likelihood, trained.n_samples, n_states, trained.n_features
        )
        aic_by_candidate[n_states] = aic(trained.log_likelihood, n_states, trained.n_features)

    if not candidates:
        raise TrainingError(
            f"every candidate state count {selection_config.candidate_states} failed to fit"
        )

    scores = (
        bic_by_candidate
        if selection_config.criterion == SelectionCriterion.BIC
        else aic_by_candidate
    )
    best_n_states = min(scores, key=lambda k: scores[k])

    return SelectionResult(
        trained_model=candidates[best_n_states],
        criterion=selection_config.criterion,
        bic_by_candidate=bic_by_candidate,
        aic_by_candidate=aic_by_candidate,
    )


__all__ = ["SelectionResult", "aic", "bic", "select"]
