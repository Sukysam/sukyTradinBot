"""Feature-level validation: output-shape sanity checks and quality-flag
computation.

Distinct from `market_data.validation`, which validates raw bars *before*
they reach this platform (missing bars, duplicate timestamps, timezone
normalization, split adjustment — all reused directly by
`pipeline.FeaturePipeline`, not reimplemented here). This module validates
what comes *out* of a feature's `compute` function.
"""

from __future__ import annotations

import pandas as pd

from features.errors import FeatureComputationError
from features.registry import FeatureSpec


def validate_feature_output(spec: FeatureSpec, output: pd.Series, expected_index: pd.Index) -> None:
    """Raise `FeatureComputationError` if `output` doesn't match the shape
    every feature's `compute` function is required to produce: a
    `pd.Series` aligned exactly to `expected_index` (the input OHLCV
    DataFrame's index). Catches a broken feature function immediately,
    with the offending feature's name in the error, rather than letting a
    misaligned or wrong-length Series silently corrupt every
    `FeatureVector` built from it.
    """
    if not isinstance(output, pd.Series):
        raise FeatureComputationError(
            f"Feature {spec.name!r}: compute() must return a pandas Series, "
            f"got {type(output).__name__}"
        )
    if len(output) != len(expected_index):
        raise FeatureComputationError(
            f"Feature {spec.name!r}: compute() returned {len(output)} values, "
            f"expected {len(expected_index)} (one per input row)"
        )
    if not output.index.equals(expected_index):
        raise FeatureComputationError(
            f"Feature {spec.name!r}: compute() output index does not match the "
            "input DataFrame's index — every feature must return a Series aligned "
            "to its input, never reindexed, reset, or reordered."
        )


def compute_quality_flags(feature_df: pd.DataFrame) -> pd.DataFrame:
    """For each feature column, `True` at rows where the value is `NaN`.

    A feature that hasn't accumulated enough trailing history for its
    `lookback` window emits `NaN` by construction (every rolling
    computation in this platform uses `min_periods=window`) — this is the
    single, uniform signal quality flags are built from, rather than each
    feature independently tracking "am I past my warmup period."
    """
    return feature_df.isna()


__all__ = ["compute_quality_flags", "validate_feature_output"]
