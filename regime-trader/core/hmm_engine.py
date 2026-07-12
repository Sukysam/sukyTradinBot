"""Gaussian HMM volatility-regime engine: Baum-Welch training with BIC model
selection, and a strictly causal Forward Algorithm for live inference (Spec
Sec. 2).

Viterbi decoding (`GaussianHMM.predict` / `.decode`) and forward-backward
smoothing (`GaussianHMM.predict_proba`) are never called from this module for
live inference. Both condition the state estimate at time t on observations
that occur after t -- Viterbi via the globally optimal path, predict_proba via
the backward pass. `forward_algorithm` and `ForwardFilter` below implement the
forward recursion directly from the fitted model's parameters so that P(S_t)
is provably a function of X_{1:t} only, by construction rather than by care at
each call site.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from hmmlearn.hmm import GaussianHMM
from scipy.special import logsumexp
from scipy.stats import multivariate_normal

logger = logging.getLogger(__name__)

MIN_COMPONENTS = 3
MAX_COMPONENTS = 7
LOG_FLOOR = 1e-300  # clip before log() so exact-zero probabilities don't produce -inf


def _n_free_parameters(n_components: int, n_features: int) -> int:
    """Free parameter count for a full-covariance GaussianHMM, used by BIC."""
    transition_params = n_components * (n_components - 1)
    start_prob_params = n_components - 1
    mean_params = n_components * n_features
    cov_params = n_components * n_features * (n_features + 1) // 2
    return transition_params + start_prob_params + mean_params + cov_params


def _bic(log_likelihood: float, n_samples: int, n_components: int, n_features: int) -> float:
    k = _n_free_parameters(n_components, n_features)
    return -2.0 * log_likelihood + k * np.log(n_samples)


@dataclass
class BICSelectionResult:
    model: GaussianHMM
    n_components: int
    bic: float
    log_likelihood: float
    scores_by_k: dict = field(default_factory=dict)


def fit_with_bic_selection(
    X: np.ndarray,
    min_components: int = MIN_COMPONENTS,
    max_components: int = MAX_COMPONENTS,
    n_init: int = 5,
    n_iter: int = 200,
    tol: float = 1e-4,
    random_state: int = 42,
) -> BICSelectionResult:
    """Fit GaussianHMM(covariance_type='full') via Baum-Welch/EM for each
    component count in [min_components, max_components] and return the fit
    that minimizes BIC.

    Each candidate K is fit `n_init` times from different random
    initializations and only the highest-log-likelihood fit is kept for that
    K: EM converges to a local optimum, so a single unlucky initialization can
    make a good K look worse than a bad K that happened to init well.
    """
    if X.ndim != 2:
        raise ValueError(f"X must be 2D (n_samples, n_features), got shape {X.shape}")
    if np.isnan(X).any():
        raise ValueError("X contains NaN values; drop or impute warmup rows before fitting")

    n_samples, n_features = X.shape
    scores_by_k: dict[int, float] = {}
    best: BICSelectionResult | None = None

    for k in range(min_components, max_components + 1):
        best_model_for_k = None
        best_ll_for_k = -np.inf

        for init_idx in range(n_init):
            model = GaussianHMM(
                n_components=k,
                covariance_type="full",
                n_iter=n_iter,
                tol=tol,
                random_state=random_state + init_idx,
            )
            try:
                model.fit(X)
                ll = model.score(X)
            except Exception as exc:
                logger.warning("HMM fit failed for K=%d, init=%d: %s", k, init_idx, exc)
                continue

            if ll > best_ll_for_k:
                best_ll_for_k = ll
                best_model_for_k = model

        if best_model_for_k is None:
            logger.warning("All initializations failed for K=%d; skipping", k)
            continue

        bic = _bic(best_ll_for_k, n_samples, k, n_features)
        scores_by_k[k] = bic
        logger.info("K=%d: log-likelihood=%.2f, BIC=%.2f", k, best_ll_for_k, bic)

        if best is None or bic < best.bic:
            best = BICSelectionResult(
                model=best_model_for_k,
                n_components=k,
                bic=bic,
                log_likelihood=best_ll_for_k,
            )

    if best is None:
        raise RuntimeError("HMM fitting failed for every candidate component count")

    best.scores_by_k = scores_by_k
    return best


def _log_emission_matrix(X: np.ndarray, means: np.ndarray, covars: np.ndarray) -> np.ndarray:
    """log N(x_t; mu_i, Sigma_i) for every (t, i). Shape (n_samples, n_components).

    `allow_singular=True` -- a fitted component's covariance can be exactly
    singular (e.g. a constant feature collapses every observation to the
    same point, giving a rank-deficient sample covariance). scipy's default
    (`False`) raises `LinAlgError` in that case; `True` falls back to the
    Moore-Penrose pseudo-inverse, the standard way to evaluate a degenerate
    Gaussian's density, and is a no-op for the common well-conditioned case.
    """
    n_samples = X.shape[0]
    n_components = means.shape[0]
    log_b = np.empty((n_samples, n_components))
    for i in range(n_components):
        log_b[:, i] = multivariate_normal.logpdf(X, mean=means[i], cov=covars[i], allow_singular=True)
    return log_b


def forward_algorithm(model: GaussianHMM, X: np.ndarray) -> np.ndarray:
    """Batch Forward Algorithm: filtered state probabilities P(S_t | X_{1:t})
    for every t in X, using only observations at or before t.

    This is the sanctioned inference path for regime probabilities over a
    historical window (e.g. backtesting, context-snapshot reconstruction). For
    a live bar-by-bar loop, use `ForwardFilter` instead so cost per bar stays
    O(n_components^2) rather than O(t * n_components^2).

    Do not substitute `model.predict_proba` (forward-backward/smoothed) or
    `model.predict` / `model.decode` (Viterbi) for this function: both
    incorporate observations after t into the estimate at t.

    Returns array of shape (n_samples, n_components).
    """
    if X.ndim != 2:
        raise ValueError(f"X must be 2D (n_samples, n_features), got shape {X.shape}")

    log_startprob = np.log(np.clip(model.startprob_, LOG_FLOOR, None))
    log_transmat = np.log(np.clip(model.transmat_, LOG_FLOOR, None))
    log_b = _log_emission_matrix(X, model.means_, model.covars_)

    n_samples, n_components = log_b.shape
    log_alpha = np.empty((n_samples, n_components))

    log_alpha[0] = log_startprob + log_b[0]
    for t in range(1, n_samples):
        log_alpha[t] = logsumexp(log_alpha[t - 1][:, None] + log_transmat, axis=0) + log_b[t]

    log_norm = logsumexp(log_alpha, axis=1, keepdims=True)
    return np.exp(log_alpha - log_norm)


class ForwardFilter:
    """Incremental (online) Forward Algorithm for live, bar-by-bar inference.

    Call `update(x_t)` once per new observation; each call is O(n_components^2)
    regardless of how much history has already been processed, since only the
    previous log-alpha vector is retained as state -- never the full
    observation history. This is what makes it safe to run inside the 5-minute
    structural loop indefinitely.
    """

    def __init__(self, model: GaussianHMM):
        self.model = model
        self.n_components = model.n_components
        self._log_startprob = np.log(np.clip(model.startprob_, LOG_FLOOR, None))
        self._log_transmat = np.log(np.clip(model.transmat_, LOG_FLOOR, None))
        self._log_alpha: np.ndarray | None = None
        self.n_updates = 0

    def reset(self) -> None:
        """Clear filter state, e.g. when swapping in a newly retrained model."""
        self._log_alpha = None
        self.n_updates = 0

    def update(self, x_t: np.ndarray) -> np.ndarray:
        """Advance the filter by one observation, return P(S_t | X_{1:t})."""
        x_t = np.asarray(x_t, dtype=float).reshape(1, -1)
        if np.isnan(x_t).any():
            raise ValueError("update() received a NaN feature vector")

        log_b_t = _log_emission_matrix(x_t, self.model.means_, self.model.covars_)[0]

        if self._log_alpha is None:
            self._log_alpha = self._log_startprob + log_b_t
        else:
            self._log_alpha = (
                logsumexp(self._log_alpha[:, None] + self._log_transmat, axis=0) + log_b_t
            )

        self.n_updates += 1
        log_norm = logsumexp(self._log_alpha)
        return np.exp(self._log_alpha - log_norm)
