"""Deterministic `FeatureVector` fixtures for `hmm` tests -- directly
constructed (not run through `FeaturePipeline`) so quantitative tests get
exact control over synthetic regime structure. See
`tests/hmm/test_service_integration.py` for a test that instead runs the
real `FeaturePipeline` end to end.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

import numpy as np
import numpy.typing as npt

from features.feature_vector import FeatureVector, Provenance

UTC = timezone.utc
DEFAULT_START = datetime(2024, 1, 1, tzinfo=UTC)


def make_feature_vectors(
    X: npt.NDArray[np.float64],
    feature_names: tuple[str, ...],
    *,
    symbol: str = "TEST",
    start: datetime = DEFAULT_START,
    delta: timedelta = timedelta(days=1),
    feature_versions: Mapping[str, int] | None = None,
    pipeline_version: str = "2",
    source_dataset: str = "synthetic",
) -> list[FeatureVector]:
    """One `FeatureVector` per row of `X` (shape `(n, len(feature_names))`),
    ascending timestamps `delta` apart starting at `start`. All vectors
    share one `Provenance` instance (mirrors `FeaturePipeline.
    compute_series`'s "one clock read per batch" behavior).
    """
    if X.ndim != 2 or X.shape[1] != len(feature_names):
        raise ValueError(f"X shape {X.shape} doesn't match {len(feature_names)} feature_names")
    resolved_versions = feature_versions or dict.fromkeys(feature_names, 1)
    provenance = Provenance(
        pipeline_version=pipeline_version,
        manifest_version="1",
        feature_versions=dict(resolved_versions),
        generated_at=start,
        source_dataset=source_dataset,
    )
    vectors = []
    for i in range(X.shape[0]):
        vectors.append(
            FeatureVector(
                timestamp=start + i * delta,
                symbol=symbol,
                feature_values=tuple(float(v) for v in X[i]),
                feature_names=feature_names,
                metadata={},
                quality_flags={},
                provenance=provenance,
            )
        )
    return vectors


def synthetic_regime_matrix(
    rng: np.random.Generator,
    *,
    regime_means: list[tuple[float, ...]],
    n_per_regime: int,
    std: float = 1.0,
) -> npt.NDArray[np.float64]:
    """Concatenate `len(regime_means)` Gaussian clusters, `n_per_regime`
    rows each, independent noise per feature dimension (never perfectly
    collinear -- a perfectly collinear feature pair produces a singular
    covariance matrix the causal forward algorithm's `scipy.stats.
    multivariate_normal.logpdf` call can't evaluate; see
    `inference.forward_algorithm`).
    """
    n_features = len(regime_means[0])
    blocks = [
        rng.normal(loc=mean, scale=std, size=(n_per_regime, n_features)) for mean in regime_means
    ]
    return np.concatenate(blocks, axis=0)
