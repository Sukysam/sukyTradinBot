"""Regression tests for the `RegimeState` contract itself (Standards/
RegimeState Contract.md), distinct from `tests/hmm/`'s own unit tests --
these exist to catch an accidental breaking change to the contract's
*shape*, not to test HMM training/inference logic. If a change here
forces an edit to this file, that's a signal the change needs a new ADR
per that Standards document's own versioning policy.
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timezone

import pytest

from hmm.models import RegimeState

UTC = timezone.utc


def _state(**overrides: object) -> RegimeState:
    defaults: dict[str, object] = {
        "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
        "symbol": "AAPL",
        "regime_id": 0,
        "confidence": 0.8,
        "transition_probability": 0.9,
        "model_version": "v1",
        "feature_pipeline_version": "2",
        "metadata": {},
    }
    defaults.update(overrides)
    return RegimeState(**defaults)  # type: ignore[arg-type]


class TestRequiredFields:
    def test_regime_state_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(RegimeState)}
        assert field_names == {
            "timestamp",
            "symbol",
            "regime_id",
            "confidence",
            "transition_probability",
            "model_version",
            "feature_pipeline_version",
            "metadata",
        }


class TestSerializationRoundTrip:
    def test_state_round_trips_through_dict(self) -> None:
        state = _state(metadata={"regime_probabilities": [0.2, 0.8], "n_states": 2})
        assert RegimeState.from_dict(state.to_dict()) == state

    def test_state_to_dict_is_json_serializable(self) -> None:
        json.dumps(_state().to_dict())


class TestBackwardCompatibility:
    def test_construction_tolerates_unknown_metadata_keys(self) -> None:
        # RegimeState.metadata has no ValueError-enforced key restriction
        # (unlike FeatureVector.quality_flags) -- any key is accepted,
        # matching the additive-only metadata policy.
        _state(metadata={"regime_probabilities": [1.0], "a_brand_new_key": 123})


class TestInvariantsEnforcedAtTypeLevel:
    @pytest.mark.parametrize("bad_value", [-0.01, 1.01])
    def test_confidence_bounded_to_zero_one(self, bad_value: float) -> None:
        with pytest.raises(ValueError, match="confidence"):
            _state(confidence=bad_value)

    @pytest.mark.parametrize("bad_value", [-0.01, 1.01])
    def test_transition_probability_bounded_to_zero_one(self, bad_value: float) -> None:
        with pytest.raises(ValueError, match="transition_probability"):
            _state(transition_probability=bad_value)

    def test_regime_id_cannot_be_negative(self) -> None:
        with pytest.raises(ValueError, match="regime_id"):
            _state(regime_id=-1)
