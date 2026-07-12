"""Deterministic fixtures for `strategy` tests."""

from __future__ import annotations

from datetime import datetime, timezone

from features.feature_vector import FeatureVector, Provenance
from hmm.models import RegimeState

UTC = timezone.utc
DEFAULT_TIMESTAMP = datetime(2024, 1, 1, tzinfo=UTC)


def make_feature_vector(
    *,
    symbol: str = "TEST",
    timestamp: datetime = DEFAULT_TIMESTAMP,
    feature_names: tuple[str, ...] = ("f1",),
    feature_values: tuple[float, ...] = (1.0,),
) -> FeatureVector:
    provenance = Provenance(
        pipeline_version="2",
        manifest_version="1",
        feature_versions=dict.fromkeys(feature_names, 1),
        generated_at=timestamp,
        source_dataset="test",
    )
    return FeatureVector(
        timestamp=timestamp,
        symbol=symbol,
        feature_values=feature_values,
        feature_names=feature_names,
        metadata={},
        quality_flags={},
        provenance=provenance,
    )


def make_regime_state(
    *,
    symbol: str = "TEST",
    timestamp: datetime = DEFAULT_TIMESTAMP,
    regime_id: int = 0,
    confidence: float = 0.8,
    transition_probability: float = 0.9,
    model_version: str = "v1",
    feature_pipeline_version: str = "2",
) -> RegimeState:
    return RegimeState(
        timestamp=timestamp,
        symbol=symbol,
        regime_id=regime_id,
        confidence=confidence,
        transition_probability=transition_probability,
        model_version=model_version,
        feature_pipeline_version=feature_pipeline_version,
        metadata={"regime_probabilities": (confidence, 1.0 - confidence), "n_states": 2},
    )
