"""`Strategy` -- the `Protocol` every registered strategy implements,
continuing the pattern established in `market_data.interfaces`/`hmm.
interfaces.Normalizer`: define the interface before implementing against
it, so a new strategy is a new class satisfying this `Protocol`, never a
change to `registry.py` or `service.py`.
"""

from __future__ import annotations

from typing import Protocol

from features.feature_vector import FeatureVector
from hmm.models import RegimeState
from strategy.models import StrategyDecision


class Strategy(Protocol):
    """A strategy is a pure function of `(FeatureVector, RegimeState)` to
    `StrategyDecision`, plus a self-declared `supports(regime_id)` capability
    check. `supports` is the *only* thing `StrategyRegistry.resolve` uses
    to route a regime to a strategy -- there is no second, independently-
    maintained routing table for it to drift out of sync with.
    """

    @property
    def strategy_id(self) -> str:
        """Unique identifier this strategy is registered under."""
        ...

    def supports(self, regime_id: int) -> bool:
        """Whether this strategy applies to `regime_id`. `regime_id` has
        no fixed meaning across trained HMM models (see Standards/
        RegimeState Contract.md) -- which regime_ids a given strategy
        instance supports is always caller/config-supplied per trained
        model, never hardcoded by this method's implementation.
        """
        ...

    def allocate(
        self, feature_vector: FeatureVector, regime_state: RegimeState
    ) -> StrategyDecision:
        """Produce a decision for `regime_state.regime_id`. Deliberately
        does *not* require `self.supports(regime_state.regime_id)` to be
        `True` -- `supports` is a dispatch-time filter for
        `StrategyRegistry.resolve`, not a precondition of `allocate`
        itself, so a strategy configured as `StrategyEngineConfig.
        default_strategy_id` can still be called for a regime it doesn't
        directly support. Implementations should validate `feature_vector`/
        `regime_state` consistency (matching `symbol`/`timestamp`), raising
        `strategy.exceptions.ContractViolationError` if they disagree.
        """
        ...


__all__ = ["Strategy"]
