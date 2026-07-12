"""Feature Engineering Platform (Milestone 3).

One canonical pipeline from raw bars to a `FeatureVector`, so HMM,
backtesting, adaptive learning, NLP, and risk never compute the same
indicator two different ways. See
docs/engineering-handbook/Architecture/ADR/ADR-003-Feature-Engineering.md.

Importing this package registers every built-in feature (price,
volatility, trend, volume, market structure, statistical, regime) into
`registry.DEFAULT_REGISTRY` as a side effect of importing the category
modules below — `FeaturePipeline()` with no arguments uses that registry.
"""

from __future__ import annotations

# Imported for registration side effects: each module's `@feature(...)`
# decorators populate `registry.DEFAULT_REGISTRY` on import. Order doesn't
# matter -- every feature computes from the same raw OHLCV DataFrame
# independently (see registry.FeatureSpec's docstring on `depends_on`
# being documentation, not a computation dependency).
from features import (  # noqa: F401
    market_structure,
    price,
    regime,
    statistical,
    trend,
    volatility,
    volume,
)
from features.errors import FeatureComputationError, FeatureError, InsufficientHistoryError
from features.feature_vector import FeatureVector
from features.pipeline import PIPELINE_VERSION, FeaturePipeline, PipelineDiagnostics
from features.registry import (
    DEFAULT_REGISTRY,
    FeatureCategory,
    FeatureRegistry,
    FeatureSpec,
    feature,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_REGISTRY",
    "PIPELINE_VERSION",
    "FeatureCategory",
    "FeatureComputationError",
    "FeatureError",
    "FeaturePipeline",
    "FeatureRegistry",
    "FeatureSpec",
    "FeatureVector",
    "InsufficientHistoryError",
    "PipelineDiagnostics",
    "__version__",
    "feature",
]
