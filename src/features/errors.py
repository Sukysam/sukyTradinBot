"""Feature-platform exception hierarchy, matching
`market_data.errors`'s pattern: every exception here derives from
`common.errors.AppError` so calling code can catch "something in this
platform's own infrastructure went wrong" without also catching unrelated
third-party exceptions.
"""

from __future__ import annotations

from common.errors import AppError


class FeatureError(AppError):
    """Base class for all feature-platform errors."""


class FeatureComputationError(FeatureError):
    """Raised when a registered feature's `compute` function raises, or
    returns output that doesn't match the pipeline's contract (wrong
    length, misaligned index) — wraps the underlying failure so a caller
    never needs to know which specific feature function is at fault to
    handle it, only that feature computation failed.
    """


class InsufficientHistoryError(FeatureError):
    """Raised when the input bar history is shorter than the longest
    `lookback` among the features being computed, for callers that need a
    hard failure rather than a `FeatureVector` full of NaN/flagged values
    (see `pipeline.FeaturePipeline.compute`'s `strict` parameter).
    """


__all__ = ["FeatureComputationError", "FeatureError", "InsufficientHistoryError"]
