"""`arbitrate` -- the module-level convenience entry point, defaulting to
`orchestration.policies.SafetyFirstPolicy` (Phase A's original single
deterministic rule). Kept as a free function for backward compatibility
with Phase A's own call sites and tests; pass `policy=` to use one of
Phase B's other three `ArbitrationPolicy` implementations instead.

Deliberately no execution, no broker, no risk in this module -- neither
`arbitrate` nor any `ArbitrationPolicy` implementation submits an order
or touches `risk.RiskService`. Per ADR-020, wiring `FinalDecision` into
the execution path is a separate, later, explicitly authorized decision.
"""

from __future__ import annotations

from memory.models import LearningDecision
from nlp.models import NewsSignal
from orchestration.config import OrchestrationConfig
from orchestration.interfaces import ArbitrationPolicy
from orchestration.models import FinalDecision
from orchestration.policies.safety_first import SafetyFirstPolicy
from strategy.models import StrategyDecision

_DEFAULT_CONFIG = OrchestrationConfig()


def arbitrate(
    strategy_decision: StrategyDecision,
    learning_decision: LearningDecision | None,
    news_signal: NewsSignal | None,
    *,
    config: OrchestrationConfig = _DEFAULT_CONFIG,
    policy: ArbitrationPolicy | None = None,
) -> FinalDecision:
    """Arbitrate `strategy_decision` (primary) against optional advisory
    `learning_decision`/`news_signal`, via `policy` (default
    `SafetyFirstPolicy(config=config)`). Raises `MismatchedSignalError`
    if a supplied advisory signal doesn't share the primary decision's
    context. Every `ArbitrationPolicy` is deterministic and side-effect-
    free -- calling this twice with the same inputs and policy always
    produces an equal `FinalDecision`."""
    active_policy = policy if policy is not None else SafetyFirstPolicy(config=config)
    return active_policy.arbitrate(strategy_decision, learning_decision, news_signal)


__all__ = ["arbitrate"]
