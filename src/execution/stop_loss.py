"""`StopLossPolicy` implementations.

`core/risk_manager.py`'s own comment references a stop derived from
"volatility tier" (Spec Sec. 3), but no concrete formula for that tier
mapping exists anywhere in this codebase to port from -- both policies
here are new, grounded in `src/features`'s existing ATR feature rather
than an unfound legacy formula. See ADR-013 for why this is a deliberate
new design rather than a port.
"""

from __future__ import annotations

from dataclasses import dataclass

from execution.models import ExecutionContext, FeatureSnapshot

DEFAULT_ATR_MULTIPLIER = 2.0
DEFAULT_FIXED_PERCENT = 0.02


@dataclass(frozen=True)
class ATRStopPolicy:
    """Stop set `atr_multiplier` average-true-ranges below the reference
    price -- a standard systematic-trading stop-sizing technique, scaled
    to each symbol's own recent volatility rather than a fixed
    percentage. The default policy; prefer this one unless a symbol's
    `FeatureSnapshot.atr_14` is unavailable or zero.
    """

    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER

    def __post_init__(self) -> None:
        if self.atr_multiplier <= 0:
            raise ValueError(f"atr_multiplier must be > 0, got {self.atr_multiplier}")

    @property
    def name(self) -> str:
        return "atr_stop"

    def compute_stop_loss(
        self, context: ExecutionContext, feature_snapshot: FeatureSnapshot
    ) -> float:
        return context.reference_price - (self.atr_multiplier * feature_snapshot.atr_14)


@dataclass(frozen=True)
class FixedPercentPolicy:
    """Stop set a fixed percentage below the reference price, ignoring
    `FeatureSnapshot` entirely -- the fallback when a symbol's ATR is
    zero or otherwise unusable (e.g. too little bar history for a
    reliable reading), so `OrderBuilder` always has a policy that can
    produce a valid stop.
    """

    percent: float = DEFAULT_FIXED_PERCENT

    def __post_init__(self) -> None:
        if not 0.0 < self.percent < 1.0:
            raise ValueError(f"percent must be in (0.0, 1.0), got {self.percent}")

    @property
    def name(self) -> str:
        return "fixed_percent_stop"

    def compute_stop_loss(
        self, context: ExecutionContext, feature_snapshot: FeatureSnapshot
    ) -> float:
        return context.reference_price * (1.0 - self.percent)


__all__ = ["ATRStopPolicy", "FixedPercentPolicy"]
