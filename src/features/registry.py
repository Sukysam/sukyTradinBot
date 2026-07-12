"""The feature registry: every feature this platform can compute, self-
describing, in one place — replacing the pattern of scattered feature
functions hardcoded into a single `build_feature_matrix`-style function
(see `regime-trader/data/feature_engineering.py`, which this platform
extends rather than replaces — see
docs/engineering-handbook/Architecture/ADR/ADR-003-Feature-Engineering.md).

A feature is registered once, via the `@feature(...)` decorator, and from
that point on the registry can enumerate every feature (for
`manifest.py`), validate every feature's causality declaration at
registration time (see `uses_future_data` below), and drive
`pipeline.FeaturePipeline`'s computation — a new feature never needs its
own bespoke wiring into the pipeline, only a registration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import pandas as pd

FeatureFunc = Callable[[pd.DataFrame], pd.Series]


class FeatureCategory(str, Enum):
    """Closed set of feature categories this platform organizes around —
    one Python module per category (`price.py`, `volatility.py`, ...).
    """

    PRICE = "price"
    VOLATILITY = "volatility"
    TREND = "trend"
    VOLUME = "volume"
    MARKET_STRUCTURE = "market_structure"
    STATISTICAL = "statistical"
    REGIME = "regime"


@dataclass(frozen=True)
class FeatureSpec:
    """Everything the platform needs to know about one feature, besides
    the computation itself.

    `lookback` is the number of trailing bars (inclusive of the current
    one) required before this feature can produce a non-`NaN` value —
    e.g. a 20-bar rolling window feature has `lookback=20`. Used by
    `validation.py` to set quality flags without re-deriving it from each
    function's implementation. `depends_on` names other registered
    features this one's *interpretation* depends on (not a computation
    dependency — every `compute` function takes the same raw OHLCV
    DataFrame and computes independently; `depends_on` is documentation/
    manifest metadata, e.g. `macd_signal` depending on `macd_line`).
    """

    name: str
    category: FeatureCategory
    version: int
    lookback: int
    dtype: str
    compute: FeatureFunc
    uses_future_data: bool = False
    depends_on: tuple[str, ...] = ()
    consumers: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Feature name must not be empty")
        if self.version < 1:
            raise ValueError(f"{self.name}: version must be >= 1, got {self.version}")
        if self.lookback < 1:
            raise ValueError(f"{self.name}: lookback must be >= 1, got {self.lookback}")
        if self.uses_future_data:
            # Enforced here, not just at registration, so a FeatureSpec can
            # never exist in a valid state with this flag set -- see
            # FeatureRegistry.register's docstring for why this platform
            # has no legitimate use for a future-peeking registered feature.
            raise ValueError(
                f"{self.name}: uses_future_data=True is not permitted for any feature "
                "registered in this platform's production registry — see "
                "docs/engineering-handbook/Standards/Anti-Lookahead Checklist.md. "
                "An oracle/smoothed feature for offline research must not be "
                "registered here at all."
            )


@dataclass
class FeatureRegistry:
    """A named collection of `FeatureSpec`s. `pipeline.py` uses one
    instance (`DEFAULT_REGISTRY` below) for production; tests construct
    their own empty instances to register fixtures without polluting the
    real catalog.
    """

    _specs: dict[str, FeatureSpec] = field(default_factory=dict)

    def register(self, spec: FeatureSpec) -> None:
        """Add `spec`. Raises `ValueError` on a duplicate name — a silent
        overwrite here would mean two features silently sharing one name
        in the manifest and in every `FeatureVector`, which is exactly the
        kind of ambiguity this registry exists to prevent.
        """
        if spec.name in self._specs:
            raise ValueError(
                f"Feature {spec.name!r} is already registered "
                f"(category={self._specs[spec.name].category.value}); "
                "feature names must be globally unique across all categories."
            )
        self._specs[spec.name] = spec

    def get(self, name: str) -> FeatureSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise KeyError(f"No feature registered under name {name!r}") from None

    def all(self) -> tuple[FeatureSpec, ...]:
        """All registered specs, ordered by name for deterministic
        iteration (manifest output, pipeline column order, test
        parametrization all rely on this being stable across runs).
        """
        return tuple(self._specs[name] for name in sorted(self._specs))

    def by_category(self, category: FeatureCategory) -> tuple[FeatureSpec, ...]:
        return tuple(spec for spec in self.all() if spec.category == category)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, name: str) -> bool:
        return name in self._specs


#: The production registry every category module (`price.py`, ...)
#: registers into at import time, and `pipeline.py` computes from by
#: default. Import the category modules (see `__init__.py`) before relying
#: on this being populated.
DEFAULT_REGISTRY = FeatureRegistry()


def feature(
    name: str,
    category: FeatureCategory,
    *,
    lookback: int,
    version: int = 1,
    dtype: str = "float64",
    depends_on: tuple[str, ...] = (),
    consumers: tuple[str, ...] = (),
    description: str = "",
    registry: FeatureRegistry | None = None,
) -> Callable[[FeatureFunc], FeatureFunc]:
    """Decorator: register the decorated function as a feature and return
    it unchanged, so it stays directly callable/testable on its own.

    `uses_future_data` is deliberately not a parameter here — every
    feature registered through this decorator is declared causal
    (`uses_future_data=False`, enforced by `FeatureSpec.__post_init__`).
    There is no opt-out; see that class's docstring.
    """

    def decorator(func: FeatureFunc) -> FeatureFunc:
        target = registry if registry is not None else DEFAULT_REGISTRY
        target.register(
            FeatureSpec(
                name=name,
                category=category,
                version=version,
                lookback=lookback,
                dtype=dtype,
                compute=func,
                depends_on=depends_on,
                consumers=consumers,
                description=description or (func.__doc__ or "").strip().split("\n")[0],
            )
        )
        return func

    return decorator


__all__ = ["DEFAULT_REGISTRY", "FeatureCategory", "FeatureRegistry", "FeatureSpec", "feature"]
