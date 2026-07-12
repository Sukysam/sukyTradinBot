"""Fits one `GaussianHMM` candidate via Baum-Welch/EM.

The restart/local-optimum handling here is ported directly from
`regime-trader/core/hmm_engine.py`'s `fit_with_bic_selection` -- same
library, same causality guarantee, factored into "fit exactly one
candidate state count" so `selector.py` can call it once per candidate
rather than owning its own copy of the restart logic (see
docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md).
"""

from __future__ import annotations

import logging

import numpy as np
import numpy.typing as npt
from hmmlearn.hmm import GaussianHMM

from hmm.config import TrainingConfig
from hmm.exceptions import TrainingError
from hmm.models import TrainedModel

logger = logging.getLogger(__name__)


def train(X: npt.NDArray[np.float64], n_states: int, config: TrainingConfig) -> TrainedModel:
    """Fit `GaussianHMM(n_components=n_states)` on already-normalized,
    NaN-free `X` via `config.n_init` independent random restarts, keeping
    only the highest-log-likelihood fit -- EM converges to a local
    optimum, so a single unlucky initialization can make a good state
    count look artificially bad. Deterministic: restart `i` always uses
    `random_state=config.random_state + i`, so the same `(X, n_states,
    config)` always produces the same result.

    Raises `TrainingError` if every restart fails (never returns an
    unconverged placeholder).
    """
    if X.ndim != 2:
        raise ValueError(f"X must be 2D (n_samples, n_features), got shape {X.shape}")
    if np.isnan(X).any():
        raise ValueError("X contains NaN values -- normalize and drop incomplete rows first")
    if n_states < 1:
        raise ValueError(f"n_states must be >= 1, got {n_states}")

    n_samples, n_features = X.shape
    best_model: GaussianHMM | None = None
    best_log_likelihood = -np.inf

    for init_idx in range(config.n_init):
        model = GaussianHMM(
            n_components=n_states,
            covariance_type=config.covariance_type,
            n_iter=config.n_iter,
            tol=config.tol,
            random_state=config.random_state + init_idx,
        )
        try:
            model.fit(X)
            log_likelihood = model.score(X)
        except Exception as exc:  # hmmlearn raises assorted numpy/linalg errors on a bad init
            logger.warning(
                "HMM fit failed for n_states=%d, restart=%d: %s", n_states, init_idx, exc
            )
            continue

        if log_likelihood > best_log_likelihood:
            best_log_likelihood = log_likelihood
            best_model = model

    if best_model is None:
        raise TrainingError(
            f"every one of {config.n_init} restart(s) failed for n_states={n_states}"
        )

    return TrainedModel(
        model=best_model,
        n_states=n_states,
        covariance_type=config.covariance_type,
        random_state=config.random_state,
        log_likelihood=best_log_likelihood,
        converged=bool(best_model.monitor_.converged),
        n_iter_used=int(best_model.monitor_.iter),
        n_samples=n_samples,
        n_features=n_features,
    )


__all__ = ["train"]
