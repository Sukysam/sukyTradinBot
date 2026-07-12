from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features.errors import FeatureComputationError
from features.registry import FeatureCategory, FeatureSpec
from features.validation import compute_quality_flags, validate_feature_output


def _spec() -> FeatureSpec:
    return FeatureSpec(
        name="dummy",
        category=FeatureCategory.PRICE,
        version=1,
        lookback=1,
        dtype="float64",
        compute=lambda df: df["close"],
    )


def test_validate_feature_output_accepts_correct_series() -> None:
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    validate_feature_output(_spec(), df["close"], df.index)  # must not raise


def test_validate_feature_output_rejects_non_series() -> None:
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    with pytest.raises(FeatureComputationError, match="dummy"):
        validate_feature_output(_spec(), [1.0, 2.0, 3.0], df.index)


def test_validate_feature_output_rejects_wrong_length() -> None:
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    short = pd.Series([1.0, 2.0])
    with pytest.raises(FeatureComputationError, match="expected 3"):
        validate_feature_output(_spec(), short, df.index)


def test_validate_feature_output_rejects_misaligned_index() -> None:
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    misaligned = pd.Series([1.0, 2.0, 3.0], index=[5, 6, 7])
    with pytest.raises(FeatureComputationError, match="index"):
        validate_feature_output(_spec(), misaligned, df.index)


def test_compute_quality_flags_flags_nan_values() -> None:
    feature_df = pd.DataFrame({"a": [np.nan, 1.0, 2.0], "b": [1.0, np.nan, 3.0]})
    flags = compute_quality_flags(feature_df)
    assert flags["a"].tolist() == [True, False, False]
    assert flags["b"].tolist() == [False, True, False]
