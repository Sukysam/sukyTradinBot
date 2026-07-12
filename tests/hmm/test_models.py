from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hmm.models import ModelMetadata, RegimeState

UTC = timezone.utc
NAIVE = datetime(2024, 1, 1)
AWARE = datetime(2024, 1, 1, tzinfo=UTC)
NON_UTC = datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=-5)))


def _state(**overrides: object) -> RegimeState:
    defaults: dict[str, object] = {
        "timestamp": AWARE,
        "symbol": "AAPL",
        "regime_id": 0,
        "confidence": 0.9,
        "transition_probability": 0.8,
        "model_version": "v1",
        "feature_pipeline_version": "2",
        "metadata": {},
    }
    defaults.update(overrides)
    return RegimeState(**defaults)  # type: ignore[arg-type]


def test_valid_state_constructs() -> None:
    state = _state()
    assert state.symbol == "AAPL"
    assert state.regime_id == 0


def test_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _state(timestamp=NAIVE)


def test_rejects_non_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="UTC"):
        _state(timestamp=NON_UTC)


def test_rejects_empty_symbol() -> None:
    with pytest.raises(ValueError, match="symbol"):
        _state(symbol="")


def test_rejects_negative_regime_id() -> None:
    with pytest.raises(ValueError, match="regime_id"):
        _state(regime_id=-1)


@pytest.mark.parametrize("bad_confidence", [-0.01, 1.01])
def test_rejects_confidence_out_of_bounds(bad_confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        _state(confidence=bad_confidence)


@pytest.mark.parametrize("bad_value", [-0.01, 1.01])
def test_rejects_transition_probability_out_of_bounds(bad_value: float) -> None:
    with pytest.raises(ValueError, match="transition_probability"):
        _state(transition_probability=bad_value)


def test_confidence_and_transition_probability_boundary_values_accepted() -> None:
    _state(confidence=0.0, transition_probability=0.0)
    _state(confidence=1.0, transition_probability=1.0)


def test_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    state = _state()
    with pytest.raises(FrozenInstanceError):
        state.regime_id = 1  # type: ignore[misc]


def _metadata(**overrides: object) -> ModelMetadata:
    defaults: dict[str, object] = {
        "model_version": "v1",
        "symbol": "AAPL",
        "feature_pipeline_version": "2",
        "feature_names": ("f1", "f2"),
        "feature_versions": {"f1": 1, "f2": 1},
        "training_window_start": AWARE,
        "training_window_end": AWARE + timedelta(days=10),
        "n_states": 3,
        "covariance_type": "full",
        "random_state": 42,
        "selection_criterion": "bic",
        "bic": 100.0,
        "aic": 90.0,
        "log_likelihood": -50.0,
        "n_samples": 100,
        "converged": True,
        "n_iter_used": 15,
        "trained_at": AWARE,
    }
    defaults.update(overrides)
    return ModelMetadata(**defaults)  # type: ignore[arg-type]


def test_valid_metadata_constructs() -> None:
    metadata = _metadata()
    assert metadata.n_states == 3


def test_metadata_rejects_window_start_after_end() -> None:
    with pytest.raises(ValueError, match="training_window_start"):
        _metadata(training_window_start=AWARE + timedelta(days=100))


def test_metadata_rejects_empty_feature_names() -> None:
    with pytest.raises(ValueError, match="feature_names"):
        _metadata(feature_names=(), feature_versions={})


def test_metadata_rejects_feature_versions_mismatch() -> None:
    with pytest.raises(ValueError, match="feature_versions"):
        _metadata(feature_versions={"f1": 1})


def test_metadata_round_trips_through_dict() -> None:
    metadata = _metadata()
    restored = ModelMetadata.from_dict(metadata.to_dict())
    assert restored == metadata
