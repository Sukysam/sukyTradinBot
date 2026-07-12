"""The causal Forward Algorithm: `P(S_t | X_{1:t})` for every `t`, using
only observations at or before `t`.

Ported from `regime-trader/core/hmm_engine.py`'s `forward_algorithm` --
same math, same causality guarantee. This is the *only* sanctioned
inference path in this package. `GaussianHMM.predict_proba` (forward-
backward/smoothed) and `.predict`/`.decode` (Viterbi) are never called
here or anywhere else in `hmm`: both incorporate observations *after* `t`
into the state estimate at `t`, which would make every `RegimeState`
non-causal by construction. See
docs/engineering-handbook/Standards/Anti-Lookahead Checklist.md and
docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md.

An incremental, O(1)-per-call variant (`ForwardFilter` in the ported
source) is deliberately not included here -- see ADR-007's note on
deferring genuinely stateful live inference until a consumer needs it;
`infer`/`infer_series` in `service.py` re-run this batch algorithm over a
bounded history window each call, matching `FeaturePipeline.compute`'s
own recompute-over-a-window pattern rather than maintaining server-side
filter state across calls.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from hmmlearn.hmm import GaussianHMM
from scipy.special import logsumexp
from scipy.stats import multivariate_normal

_LOG_FLOOR = 1e-300  # clip before log() so exact-zero probabilities don't produce -inf


def _log_emission_matrix(
    X: npt.NDArray[np.float64], means: npt.NDArray[np.float64], covars: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """log N(x_t; mu_i, Sigma_i) for every (t, i). Shape (n_samples, n_components).

    `allow_singular=True` -- a fitted component's covariance can be exactly
    singular (e.g. a constant feature after normalization collapses every
    observation to the same point, giving a rank-deficient sample
    covariance; see `tests/hmm/test_quantitative.py::TestConstantSeries`).
    scipy's default (`False`) raises `LinAlgError` in that case; `True`
    falls back to the Moore-Penrose pseudo-inverse, the standard way to
    evaluate a degenerate Gaussian's density, and is a no-op for the
    common well-conditioned case.
    """
    n_samples = X.shape[0]
    n_components = means.shape[0]
    log_b = np.empty((n_samples, n_components))
    for i in range(n_components):
        log_b[:, i] = multivariate_normal.logpdf(
            X, mean=means[i], cov=covars[i], allow_singular=True
        )
    return log_b


def forward_algorithm(model: GaussianHMM, X: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Filtered state probabilities `P(S_t | X_{1:t})` for every `t` in
    `X` (already normalized, NaN-free). Returns shape `(n_samples,
    n_components)`.
    """
    if X.ndim != 2:
        raise ValueError(f"X must be 2D (n_samples, n_features), got shape {X.shape}")

    log_startprob = np.log(np.clip(model.startprob_, _LOG_FLOOR, None))
    log_transmat = np.log(np.clip(model.transmat_, _LOG_FLOOR, None))
    log_b = _log_emission_matrix(X, model.means_, model.covars_)

    n_samples, n_components = log_b.shape
    log_alpha = np.empty((n_samples, n_components))

    log_alpha[0] = log_startprob + log_b[0]
    for t in range(1, n_samples):
        log_alpha[t] = logsumexp(log_alpha[t - 1][:, None] + log_transmat, axis=0) + log_b[t]

    log_norm = logsumexp(log_alpha, axis=1, keepdims=True)
    return np.asarray(np.exp(log_alpha - log_norm), dtype=np.float64)


__all__ = ["forward_algorithm"]
