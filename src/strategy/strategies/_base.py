"""`RegimeMappedStrategy` -- the shared implementation behind every
reference strategy in this package (`bull.py`, `bear.py`, `sideways.py`,
`defensive.py`). Milestone 5 is deliberately simple: a fixed target
allocation, scaled by the regime's own posterior confidence, for whichever
`regime_id`s the caller configures a given instance to support. No
portfolio construction, no optimization -- see
docs/engineering-handbook/Architecture/ADR/ADR-009-Strategy-Engine-Design.md.

`regime_id` has no fixed meaning across trained HMM models (Standards/
RegimeState Contract.md). `supported_regime_ids` is always supplied by the
caller building a given deployment's strategy set, typically after
inspecting a specific trained model's fitted state characteristics (mean
return/volatility per state) -- never hardcoded here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from features.feature_vector import FeatureVector
from hmm.models import RegimeState
from strategy.exceptions import ContractViolationError
from strategy.models import StrategyDecision


@dataclass(frozen=True)
class RegimeMappedStrategy:
    """`strategy_id` and `supported_regime_ids` are supplied per instance
    (see each `strategies/*.py` module's `create_*` factory) -- this class
    has no built-in notion of which `regime_id` means what. `style` is a
    short label used only in `reasoning` text and `metadata`, not part of
    the frozen `StrategyDecision` contract.
    """

    strategy_id: str
    supported_regime_ids: frozenset[int]
    base_allocation: float
    expected_holding_period: timedelta
    style: str

    def __post_init__(self) -> None:
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        # An empty supported_regime_ids is legal (not "must not be empty"):
        # it means this instance never matches via StrategyRegistry.
        # resolve's supports()-based dispatch, only via an explicit
        # default_strategy_id fallback -- see strategies/defensive.py.
        if not 0.0 <= self.base_allocation <= 1.0:
            raise ValueError(
                f"{self.strategy_id}: base_allocation must be in [0.0, 1.0], "
                f"got {self.base_allocation}"
            )
        if self.expected_holding_period <= timedelta(0):
            raise ValueError(
                f"{self.strategy_id}: expected_holding_period must be positive, "
                f"got {self.expected_holding_period}"
            )

    def supports(self, regime_id: int) -> bool:
        return regime_id in self.supported_regime_ids

    def allocate(
        self, feature_vector: FeatureVector, regime_state: RegimeState
    ) -> StrategyDecision:
        if feature_vector.symbol != regime_state.symbol:
            raise ContractViolationError(
                f"{self.strategy_id}: FeatureVector symbol {feature_vector.symbol!r} != "
                f"RegimeState symbol {regime_state.symbol!r}"
            )
        if feature_vector.timestamp != regime_state.timestamp:
            raise ContractViolationError(
                f"{self.strategy_id}: FeatureVector timestamp "
                f"{feature_vector.timestamp.isoformat()} != RegimeState timestamp "
                f"{regime_state.timestamp.isoformat()}"
            )
        # `supports()` is a dispatch-time filter for StrategyRegistry.resolve,
        # not a precondition of allocate() itself -- this formula doesn't
        # actually depend on regime_id being in supported_regime_ids, and
        # re-checking it here would break StrategyEngineConfig.
        # default_strategy_id's whole point: a fallback strategy is called
        # *precisely because* no strategy's supports() matched. See
        # docs/engineering-handbook/Architecture/ADR/ADR-009-Strategy-Engine-Design.md.

        # Confidence propagation: this milestone has no independent signal
        # beyond the regime call itself, so the decision's own confidence
        # *is* the regime's, and target allocation scales linearly with
        # it -- a low-confidence regime call produces a proportionally
        # smaller position, never the full base_allocation regardless of
        # how sure the HMM actually was.
        allocation = self.base_allocation * regime_state.confidence
        confidence = regime_state.confidence

        reasoning = (
            f"regime_id={regime_state.regime_id} resolved to {self.style} strategy "
            f"{self.strategy_id!r} (regime confidence {regime_state.confidence:.3f}); "
            f"target allocation {allocation:.3f} = base {self.base_allocation:.2f} x confidence."
        )
        metadata: dict[str, Any] = {
            "style": self.style,
            "base_allocation": self.base_allocation,
        }

        return StrategyDecision(
            timestamp=regime_state.timestamp,
            symbol=regime_state.symbol,
            strategy_id=self.strategy_id,
            regime_id=regime_state.regime_id,
            allocation=allocation,
            confidence=confidence,
            expected_holding_period=self.expected_holding_period,
            reasoning=reasoning,
            metadata=metadata,
        )


__all__ = ["RegimeMappedStrategy"]
