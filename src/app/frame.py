"""`RuntimeFrame` -- internal runtime plumbing, not a frozen contract.

Carries one bar's worth of state through the runtime as each phase
enriches it, so a later phase doesn't have to reconstruct or re-fetch
state an earlier phase already computed. Concretely: `strategy.service.
StrategyService.decide` needs both a `FeatureVector` and the
`RegimeState` derived from it in the same call, but
`RegimeEmitter.handle_frame` only receives the vector as an input to
`RegimeService.infer` -- without a carrier object, Phase D would have
no clean way to get the original vector back alongside the regime call
it produced. See
docs/engineering-handbook/Architecture/ADR/ADR-030-Runtime-Strategy-Engine-Design.md.

Deliberately NOT a `features`/`hmm`/`strategy`-style frozen contract:
no Standards doc, no contract-freeze ADR, no consumer outside `app`
itself. It exists only to move data between this package's own
emitters, and can change shape freely as later phases are added.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from features.feature_vector import FeatureVector
from hmm.models import RegimeState
from market_data.models import Bar
from strategy.models import StrategyDecision


@dataclass(frozen=True)
class RuntimeFrame:
    """One bar's worth of runtime state, enriched strictly in pipeline
    order (`bar` -> `feature_vector` -> `regime_state` ->
    `strategy_decision`). `__post_init__` enforces that order as an
    invariant -- a frame can't carry a `regime_state` without a
    `feature_vector`, or a `strategy_decision` without a `regime_state`
    -- catching a wiring bug in `app.bootstrap` immediately rather than
    letting a later phase silently receive a gap it didn't expect.
    """

    bar: Bar
    feature_vector: FeatureVector | None = None
    regime_state: RegimeState | None = None
    strategy_decision: StrategyDecision | None = None

    def __post_init__(self) -> None:
        if self.regime_state is not None and self.feature_vector is None:
            raise ValueError("RuntimeFrame has regime_state but no feature_vector")
        if self.strategy_decision is not None and self.regime_state is None:
            raise ValueError("RuntimeFrame has strategy_decision but no regime_state")

    def with_feature_vector(self, feature_vector: FeatureVector) -> RuntimeFrame:
        return replace(self, feature_vector=feature_vector)

    def with_regime_state(self, regime_state: RegimeState) -> RuntimeFrame:
        return replace(self, regime_state=regime_state)

    def with_strategy_decision(self, strategy_decision: StrategyDecision) -> RuntimeFrame:
        return replace(self, strategy_decision=strategy_decision)


RuntimeFrameCallback = Callable[[RuntimeFrame], None]

__all__ = ["RuntimeFrame", "RuntimeFrameCallback"]
