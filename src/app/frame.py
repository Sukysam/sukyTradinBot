"""`RuntimeFrame` -- internal runtime plumbing, not a frozen contract.

Carries one bar's worth of state through the runtime as each phase
enriches it, so a later phase doesn't have to reconstruct or re-fetch
state an earlier phase already computed. Concretely: `strategy.service.
StrategyService.decide` needs both a `FeatureVector` and the
`RegimeState` derived from it in the same call, and
`orchestration.arbitration.arbitrate` needs the `StrategyDecision`
alongside them too -- without a carrier object, each later phase would
have no clean way to get the earlier objects back alongside whatever
it produces. See
docs/engineering-handbook/Architecture/ADR/ADR-030-Runtime-Strategy-Engine-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-031-Signal-Orchestration-Design.md,
docs/engineering-handbook/Architecture/ADR/ADR-032-Runtime-Risk-Management-Design.md,
and
docs/engineering-handbook/Architecture/ADR/ADR-033-Runtime-Paper-Execution-Design.md.

Deliberately NOT a `features`/`hmm`/`strategy`-style frozen contract:
no Standards doc, no contract-freeze ADR, no consumer outside `app`
itself. It exists only to move data between this package's own
emitters, and can change shape freely as later phases are added.

Every emitter's `handle_bar`/`handle_frame` takes and returns a frame
(or `None` to signal "stop here, nothing to pass on") rather than
invoking an injected callback -- see `app.pipeline.compose_pipeline`,
which folds a first-stage `handle_bar` and any number of `handle_frame`
stages into one `on_bar`-compatible callable. This keeps every emitter
free of a "next hook" parameter and keeps composition in exactly one
place (`app.bootstrap`) instead of spread across every emitter's
constructor.

The `require_*` methods centralize "does this frame have what I need
yet" validation here, in one place, instead of every emitter repeating
its own `if frame.x is None: raise ValueError(...)` -- each is fully
typed (returns the concrete type, not `Any`), so a caller loses no
static-typing precision by using one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from execution.broker_adapter import BrokerSubmissionResult
from execution.models import OrderIntent
from features.feature_vector import FeatureVector
from hmm.models import RegimeState
from market_data.models import Bar
from orchestration.models import FinalDecision
from risk.models import ExecutionDecision
from strategy.models import StrategyDecision


@dataclass(frozen=True)
class RuntimeFrame:
    """One bar's worth of runtime state, enriched strictly in pipeline
    order (`bar` -> `feature_vector` -> `regime_state` ->
    `strategy_decision` -> `final_decision` -> `execution_decision` ->
    `order_intent` -> `broker_submission_result`). `__post_init__`
    enforces that order as an invariant -- a frame can't carry a
    `regime_state` without a `feature_vector`, and so on down the
    chain -- catching a wiring bug in `app.bootstrap` immediately
    rather than letting a later phase silently receive a gap it didn't
    expect.
    """

    bar: Bar
    feature_vector: FeatureVector | None = None
    regime_state: RegimeState | None = None
    strategy_decision: StrategyDecision | None = None
    final_decision: FinalDecision | None = None
    execution_decision: ExecutionDecision | None = None
    order_intent: OrderIntent | None = None
    broker_submission_result: BrokerSubmissionResult | None = None

    def __post_init__(self) -> None:
        if self.regime_state is not None and self.feature_vector is None:
            raise ValueError("RuntimeFrame has regime_state but no feature_vector")
        if self.strategy_decision is not None and self.regime_state is None:
            raise ValueError("RuntimeFrame has strategy_decision but no regime_state")
        if self.final_decision is not None and self.strategy_decision is None:
            raise ValueError("RuntimeFrame has final_decision but no strategy_decision")
        if self.execution_decision is not None and self.final_decision is None:
            raise ValueError("RuntimeFrame has execution_decision but no final_decision")
        if self.order_intent is not None and self.execution_decision is None:
            raise ValueError("RuntimeFrame has order_intent but no execution_decision")
        if self.broker_submission_result is not None and self.order_intent is None:
            raise ValueError("RuntimeFrame has broker_submission_result but no order_intent")

    def with_feature_vector(self, feature_vector: FeatureVector) -> RuntimeFrame:
        return replace(self, feature_vector=feature_vector)

    def with_regime_state(self, regime_state: RegimeState) -> RuntimeFrame:
        return replace(self, regime_state=regime_state)

    def with_strategy_decision(self, strategy_decision: StrategyDecision) -> RuntimeFrame:
        return replace(self, strategy_decision=strategy_decision)

    def with_final_decision(self, final_decision: FinalDecision) -> RuntimeFrame:
        return replace(self, final_decision=final_decision)

    def with_execution_decision(self, execution_decision: ExecutionDecision) -> RuntimeFrame:
        return replace(self, execution_decision=execution_decision)

    def with_order_intent(self, order_intent: OrderIntent) -> RuntimeFrame:
        return replace(self, order_intent=order_intent)

    def with_broker_submission_result(
        self, broker_submission_result: BrokerSubmissionResult
    ) -> RuntimeFrame:
        return replace(self, broker_submission_result=broker_submission_result)

    def require_feature_vector(self) -> FeatureVector:
        if self.feature_vector is None:
            raise ValueError("RuntimeFrame is missing feature_vector")
        return self.feature_vector

    def require_regime_state(self) -> RegimeState:
        if self.regime_state is None:
            raise ValueError("RuntimeFrame is missing regime_state")
        return self.regime_state

    def require_strategy_decision(self) -> StrategyDecision:
        if self.strategy_decision is None:
            raise ValueError("RuntimeFrame is missing strategy_decision")
        return self.strategy_decision

    def require_final_decision(self) -> FinalDecision:
        if self.final_decision is None:
            raise ValueError("RuntimeFrame is missing final_decision")
        return self.final_decision

    def require_execution_decision(self) -> ExecutionDecision:
        if self.execution_decision is None:
            raise ValueError("RuntimeFrame is missing execution_decision")
        return self.execution_decision

    def require_order_intent(self) -> OrderIntent:
        if self.order_intent is None:
            raise ValueError("RuntimeFrame is missing order_intent")
        return self.order_intent

    def require_broker_submission_result(self) -> BrokerSubmissionResult:
        if self.broker_submission_result is None:
            raise ValueError("RuntimeFrame is missing broker_submission_result")
        return self.broker_submission_result


__all__ = ["RuntimeFrame"]
