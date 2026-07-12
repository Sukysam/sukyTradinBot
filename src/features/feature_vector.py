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
and docs/engineering-handbook/Architecture/ADR/ADR-005-FeatureVector-Provenance.md
-- required fields, metadata schema, provenance schema, feature-ordering
guarantees, versioning policy, and backward-compatibility rules are all
documented in full at
"docs/engineering-handbook/Standards/FeatureVector Contract.md". Read that
document, not just this docstring, before changing any field here or
before building a new consumer that depends on this shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware, got naive datetime {value!r}")
    if value.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError(
            f"{field_name} must be normalized to UTC, got offset "
            f"{value.utcoffset()} for {value!r}"
        )


@dataclass(frozen=True)
class Provenance:
    """Where a `FeatureVector` came from — the answer to "is this
    reproducible" for a backtest, an audit, or a training/inference
    consistency check, rather than something a consumer has to
    reconstruct from logs or guess at.

    `pipeline_version` is `pipeline.PIPELINE_VERSION` at computation time
    (the `FeatureVector` contract's own version — see Standards/
    FeatureVector Contract.md). `manifest_version` is `manifest.
    MANIFEST_SCHEMA_VERSION` at computation time (the manifest *file's*
    schema version, not a content hash — the manifest's actual content is
    fully determined by `feature_versions` below plus the checked-in git
    state, so duplicating a content hash here would be a second source of
    truth for the same information). `feature_versions` is `{feature_name:
    FeatureSpec.version}` for exactly the features in this vector — the
    piece that lets a consumer confirm training and inference used
    identical feature definitions, not just the same feature *names*.
    `generated_at` is wall-clock computation time, distinct from
    `timestamp` (the bar's market time). `source_dataset` is a caller-
    supplied dataset identifier or cache key — even a loose, informal one
    is enough to trace a vector back to what was replayed to produce it.
    """

    pipeline_version: str
    manifest_version: str
    feature_versions: Mapping[str, int]
    generated_at: datetime
    source_dataset: str

    def __post_init__(self) -> None:
        _require_utc(self.generated_at, "generated_at")


@dataclass(frozen=True)
class FeatureVector:
    """One symbol's feature values at one point in time.

    `feature_values` and `feature_names` are parallel arrays — the name at
    index `i` describes the value at index `i`. `quality_flags` is keyed by
    feature name and is `True` for a feature whose value at this timestamp
    should be treated as suspect (most commonly: insufficient trailing
    history for its lookback window, so the value is `NaN`) — a consumer
    can filter or down-weight flagged features per-feature rather than
    discarding the whole vector. `provenance` (see `Provenance`) is what
    makes a vector traceable back to the exact pipeline/feature/manifest
    versions and dataset that produced it.
    """

    timestamp: datetime
    symbol: str
    feature_values: tuple[float, ...]
    feature_names: tuple[str, ...]
    metadata: Mapping[str, Any]
    quality_flags: Mapping[str, bool]
    provenance: Provenance

    def __post_init__(self) -> None:
        _require_utc(self.timestamp, "timestamp")
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
        provenance_names = set(self.provenance.feature_versions)
        if provenance_names != set(self.feature_names):
            raise ValueError(
                "provenance.feature_versions must cover exactly this vector's "
                f"feature_names; got {sorted(provenance_names)}, expected "
                f"{sorted(self.feature_names)}"
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


__all__ = ["FeatureVector", "Provenance"]
