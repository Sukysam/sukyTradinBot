"""Regression tests for the `FeatureVector` contract itself (Standards/
FeatureVector Contract.md), distinct from `tests/features/`'s own unit
tests -- these exist to catch an accidental breaking change to the
contract's *shape*, not to test feature computation logic. If a change
here forces an edit to this file, that's a signal the change needs a new
ADR and a `PIPELINE_VERSION` bump, per that Standards document's own
versioning policy.
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timezone

import pytest

from features.feature_vector import FeatureVector, Provenance
from features.pipeline import PIPELINE_VERSION

UTC = timezone.utc


def _provenance(**overrides: object) -> Provenance:
    defaults: dict[str, object] = {
        "pipeline_version": PIPELINE_VERSION,
        "manifest_version": "1",
        "feature_versions": {"f1": 1},
        "generated_at": datetime(2024, 1, 1, tzinfo=UTC),
        "source_dataset": "test",
    }
    defaults.update(overrides)
    return Provenance(**defaults)  # type: ignore[arg-type]


def _vector(**overrides: object) -> FeatureVector:
    defaults: dict[str, object] = {
        "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
        "symbol": "AAPL",
        "feature_values": (1.0,),
        "feature_names": ("f1",),
        "metadata": {},
        "quality_flags": {},
        "provenance": _provenance(),
    }
    defaults.update(overrides)
    return FeatureVector(**defaults)  # type: ignore[arg-type]


class TestRequiredFields:
    def test_feature_vector_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(FeatureVector)}
        assert field_names == {
            "timestamp",
            "symbol",
            "feature_values",
            "feature_names",
            "metadata",
            "quality_flags",
            "provenance",
        }

    def test_provenance_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(Provenance)}
        assert field_names == {
            "pipeline_version",
            "manifest_version",
            "feature_versions",
            "generated_at",
            "source_dataset",
        }


class TestVersionMetadata:
    def test_pipeline_version_is_currently_2(self) -> None:
        # Standards/FeatureVector Contract.md's "Contract history" -- v2
        # per ADR-005. If this assertion needs to change, that document's
        # own declared version must change in the same commit.
        assert PIPELINE_VERSION == "2"


class TestSerializationRoundTrip:
    def test_vector_round_trips_through_dict(self) -> None:
        vec = _vector()
        assert FeatureVector.from_dict(vec.to_dict()) == vec

    def test_vector_to_dict_is_json_serializable(self) -> None:
        json.dumps(_vector().to_dict())

    def test_provenance_round_trips_through_dict(self) -> None:
        prov = _provenance()
        assert Provenance.from_dict(prov.to_dict()) == prov


class TestBackwardCompatibility:
    def test_construction_tolerates_unknown_metadata_keys(self) -> None:
        # Per Standards/FeatureVector Contract.md's metadata policy:
        # consumers (and construction itself) must tolerate unknown keys
        # -- adding a new one must never break an existing caller.
        _vector(metadata={"n_bars_used": 10, "a_brand_new_key_from_the_future": 123})

    def test_quality_flags_must_reference_known_feature_names(self) -> None:
        with pytest.raises(ValueError, match="unknown feature"):
            _vector(quality_flags={"not_a_feature": True})

    def test_provenance_feature_versions_must_cover_exactly_feature_names(self) -> None:
        with pytest.raises(ValueError, match="feature_versions"):
            _vector(provenance=_provenance(feature_versions={"different_name": 1}))
