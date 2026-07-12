"""`FeatureVector` — the single contract every consumer of this platform
reads.

Per docs/engineering-handbook/Architecture/ADR/ADR-003-Feature-Engineering.md,
this is the whole point of Milestone 3: HMM, backtesting, adaptive
learning, NLP, and risk are all meant to consume exactly this type,
produced by exactly one pipeline (`pipeline.FeaturePipeline`), so feature
computation can never silently diverge between live trading, backtests,
and model training the way it does in systems that reimplement the same
indicator three times.

This type is a frozen, binding contract as of
docs/engineering-handbook/Architecture/ADR/ADR-004-FeatureVector-Contract-Freeze.md
-- required fields, metadata schema, feature-ordering guarantees,
versioning policy, and backward-compatibility rules are all documented in
full at "docs/engineering-handbook/Standards/FeatureVector Contract.md".
Read that document, not just this docstring, before changing any field
here or before building a new consumer that depends on this shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class FeatureVector:
    """One symbol's feature values at one point in time.

    `feature_values` and `feature_names` are parallel arrays — the name at
    index `i` describes the value at index `i`. `quality_flags` is keyed by
    feature name and is `True` for a feature whose value at this timestamp
    should be treated as suspect (most commonly: insufficient trailing
    history for its lookback window, so the value is `NaN`) — a consumer
    can filter or down-weight flagged features per-feature rather than
    discarding the whole vector.
    """

    timestamp: datetime
    symbol: str
    feature_values: tuple[float, ...]
    feature_names: tuple[str, ...]
    metadata: Mapping[str, Any]
    quality_flags: Mapping[str, bool]
    version: str

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                f"timestamp must be timezone-aware, got naive datetime {self.timestamp!r}"
            )
        if self.timestamp.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError(
                f"timestamp must be normalized to UTC, got offset "
                f"{self.timestamp.utcoffset()} for {self.timestamp!r}"
            )
        if len(self.feature_values) != len(self.feature_names):
            raise ValueError(
                f"feature_values ({len(self.feature_values)}) and feature_names "
                f"({len(self.feature_names)}) must be the same length"
            )
        unknown_flags = set(self.quality_flags) - set(self.feature_names)
        if unknown_flags:
            raise ValueError(
                f"quality_flags references unknown feature name(s): {sorted(unknown_flags)}"
            )

    def as_dict(self) -> dict[str, float]:
        """`{feature_name: value}` — the shape most model code actually
        wants (e.g. building a training-row dict or a DataFrame row).
        """
        return dict(zip(self.feature_names, self.feature_values))

    def get(self, name: str) -> float:
        """The value of a single named feature. Raises `KeyError` with the
        feature name if it isn't present — never returns a silent default,
        since a caller asking for a feature that doesn't exist is a bug to
        surface immediately, not paper over with e.g. `0.0` or `NaN`.
        """
        try:
            index = self.feature_names.index(name)
        except ValueError:
            raise KeyError(f"No feature named {name!r} in this FeatureVector") from None
        return self.feature_values[index]

    def is_flagged(self, name: str) -> bool:
        """Whether `name` is flagged as suspect at this timestamp. A
        feature never referenced in `quality_flags` is treated as clean
        (`False`) — flags are opt-in, not opt-out.
        """
        return self.quality_flags.get(name, False)

    @property
    def has_any_flag(self) -> bool:
        return any(self.quality_flags.values())


__all__ = ["FeatureVector"]
