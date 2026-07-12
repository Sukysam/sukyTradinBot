from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from features.feature_vector import FeatureVector

UTC = timezone.utc
NAIVE = datetime(2024, 1, 1)
AWARE = datetime(2024, 1, 1, tzinfo=UTC)
NON_UTC = datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=-5)))


def _vector(**overrides: object) -> FeatureVector:
    defaults: dict[str, object] = {
        "timestamp": AWARE,
        "symbol": "AAPL",
        "feature_values": (1.0, 2.0),
        "feature_names": ("a", "b"),
        "metadata": {"source": "test"},
        "quality_flags": {},
        "version": "1",
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
