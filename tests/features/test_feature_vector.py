from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from features.feature_vector import FeatureVector, Provenance

UTC = timezone.utc
NAIVE = datetime(2024, 1, 1)
AWARE = datetime(2024, 1, 1, tzinfo=UTC)
NON_UTC = datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=-5)))


def _provenance(**overrides: object) -> Provenance:
    defaults: dict[str, object] = {
        "pipeline_version": "2",
        "manifest_version": "1",
        "feature_versions": {"a": 1, "b": 1},
        "generated_at": AWARE,
        "source_dataset": "test",
    }
    defaults.update(overrides)
    return Provenance(**defaults)  # type: ignore[arg-type]


def _vector(**overrides: object) -> FeatureVector:
    defaults: dict[str, object] = {
        "timestamp": AWARE,
        "symbol": "AAPL",
        "feature_values": (1.0, 2.0),
        "feature_names": ("a", "b"),
        "metadata": {},
        "quality_flags": {},
        "provenance": _provenance(),
    }
    defaults.update(overrides)
    return FeatureVector(**defaults)  # type: ignore[arg-type]


def test_valid_vector_constructs() -> None:
    vec = _vector()
    assert vec.symbol == "AAPL"
    assert vec.get("a") == 1.0
    assert vec.get("b") == 2.0


def test_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _vector(timestamp=NAIVE)


def test_rejects_non_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="UTC"):
        _vector(timestamp=NON_UTC)


def test_rejects_mismatched_values_and_names_length() -> None:
    with pytest.raises(ValueError, match="same length"):
        _vector(feature_values=(1.0, 2.0, 3.0), feature_names=("a", "b"))


def test_rejects_quality_flag_for_unknown_feature() -> None:
    with pytest.raises(ValueError, match="unknown feature"):
        _vector(quality_flags={"not_a_feature": True})


def test_as_dict() -> None:
    vec = _vector()
    assert vec.as_dict() == {"a": 1.0, "b": 2.0}


def test_get_unknown_feature_raises_key_error() -> None:
    vec = _vector()
    with pytest.raises(KeyError, match="nonexistent"):
        vec.get("nonexistent")


def test_is_flagged_defaults_to_false_for_unflagged_feature() -> None:
    vec = _vector(quality_flags={"a": True})
    assert vec.is_flagged("a") is True
    assert vec.is_flagged("b") is False


def test_has_any_flag() -> None:
    assert _vector(quality_flags={}).has_any_flag is False
    assert _vector(quality_flags={"a": False}).has_any_flag is False
    assert _vector(quality_flags={"a": True}).has_any_flag is True


def test_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    vec = _vector()
    with pytest.raises(FrozenInstanceError):
        vec.symbol = "MSFT"  # type: ignore[misc]


def test_provenance_is_accessible_on_the_vector() -> None:
    vec = _vector()
    assert vec.provenance.pipeline_version == "2"
    assert vec.provenance.manifest_version == "1"
    assert vec.provenance.feature_versions == {"a": 1, "b": 1}
    assert vec.provenance.source_dataset == "test"


def test_rejects_provenance_feature_versions_missing_a_feature() -> None:
    with pytest.raises(ValueError, match=r"provenance\.feature_versions"):
        _vector(provenance=_provenance(feature_versions={"a": 1}))


def test_rejects_provenance_feature_versions_with_extra_feature() -> None:
    with pytest.raises(ValueError, match=r"provenance\.feature_versions"):
        _vector(provenance=_provenance(feature_versions={"a": 1, "b": 1, "c": 1}))


def test_provenance_rejects_naive_generated_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _provenance(generated_at=NAIVE)


def test_provenance_rejects_non_utc_generated_at() -> None:
    with pytest.raises(ValueError, match="UTC"):
        _provenance(generated_at=NON_UTC)


def test_provenance_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    prov = _provenance()
    with pytest.raises(FrozenInstanceError):
        prov.source_dataset = "other"  # type: ignore[misc]


def test_provenance_round_trips_through_dict() -> None:
    prov = _provenance()
    assert Provenance.from_dict(prov.to_dict()) == prov


def test_vector_round_trips_through_dict() -> None:
    vec = _vector(metadata={"n_bars_used": 10}, quality_flags={"a": True})
    assert FeatureVector.from_dict(vec.to_dict()) == vec


def test_vector_to_dict_is_json_serializable() -> None:
    import json

    vec = _vector()
    json.dumps(vec.to_dict())
