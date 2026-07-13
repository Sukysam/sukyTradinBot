"""Settings shared across `RiskService.default`'s assembly of a sensible
default validator/sizing-rule set. Individual `RiskValidator`/`SizingRule`
implementations still take their own thresholds directly as constructor
arguments -- this only holds what that default assembly itself needs,
mirroring `strategy.config.StrategyEngineConfig`'s "one real knob, not a
speculative grab-bag" precedent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RiskServiceConfig:
    sector_map: Mapping[str, str] = field(default_factory=dict)
    """Symbol -> sector, consumed by `SectorExposureValidator`/
    `ExposureCapacitySizing` when `RiskService.default` builds them. Empty
    by default -- a symbol missing from this map skips the sector check
    entirely rather than fabricating a sector, the same documented no-op
    `Architecture/Known Gaps.md` item 1 already describes for `main.py`'s
    own empty `sectors={}` today."""


__all__ = ["RiskServiceConfig"]
