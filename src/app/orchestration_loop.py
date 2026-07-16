"""`OrchestrationEmitter` -- Phase E: the stage after `StrategyEmitter`
in the composed pipeline, wired to `orchestration.arbitration.arbitrate`.
See
docs/engineering-handbook/Architecture/ADR/ADR-031-Signal-Orchestration-Design.md.

`handle_frame` is the whole surface: call `arbitrate` with
`frame.strategy_decision` (primary) and whatever advisory
`LearningDecision`/`NewsSignal` the optional providers return, log one
structured event per computed `FinalDecision`, record it on an
`ops.metrics.MetricsRegistry`, and return the enriched frame -- or
`None` on failure. A failure is caught and logged, never propagated,
matching `StrategyEmitter`'s own failure-isolation convention.

`learning_decision_provider`/`news_signal_provider` are optional and
default to `None` (meaning: no advisory input, ever) -- there is no
`MemoryEmitter`/`NlpEmitter` stage in this runtime, by design (per
direct instruction). Milestones 9 and 10 built `memory`/`nlp` as
shadow-mode-only: `arbitrate` already treats a missing advisory signal
as the ordinary case (`SignalInput(considered=False, ...)`), not a
degraded one, so omitting both providers here isn't a workaround -- it
is exactly what running this runtime with no live Memory/NLP wiring
is supposed to look like. A provider that *is* supplied is expected to
return `None` for "nothing to contribute right now"; a raised
exception from a provider is caught the same as an `arbitrate` failure
-- an advisory source misbehaving must never block the primary
decision.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from app.frame import RuntimeFrame
from memory.models import LearningDecision
from nlp.models import NewsSignal
from ops.metrics import MetricsRegistry
from orchestration.arbitration import arbitrate
from orchestration.config import OrchestrationConfig
from orchestration.exceptions import OrchestrationError
from orchestration.interfaces import ArbitrationPolicy
from strategy.models import StrategyDecision

logger = logging.getLogger(__name__)

# `Optional[...]`, not `X | None` -- see app.pipeline.FrameStage's
# comment on why (a runtime type-alias assignment, needs Python 3.9
# compatibility).
LearningDecisionProvider = Callable[[StrategyDecision], Optional[LearningDecision]]
NewsSignalProvider = Callable[[StrategyDecision], Optional[NewsSignal]]


class OrchestrationEmitter:
    """Wraps `arbitrate` (default policy: `SafetyFirstPolicy`, unless
    `policy` is given). Holds no "next stage" hook -- see
    `app.pipeline.compose_pipeline` for how this is wired to whatever
    comes after it in a future phase.
    """

    def __init__(
        self,
        *,
        policy: ArbitrationPolicy | None = None,
        config: OrchestrationConfig | None = None,
        learning_decision_provider: LearningDecisionProvider | None = None,
        news_signal_provider: NewsSignalProvider | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._policy = policy
        self._config = config or OrchestrationConfig()
        self._learning_decision_provider = learning_decision_provider
        self._news_signal_provider = news_signal_provider
        self._metrics = metrics or MetricsRegistry()

    @property
    def metrics(self) -> MetricsRegistry:
        return self._metrics

    def _learning_decision(self, decision: StrategyDecision) -> LearningDecision | None:
        if self._learning_decision_provider is None:
            return None
        try:
            return self._learning_decision_provider(decision)
        except Exception as exc:
            logger.warning(
                "learning_decision_provider failed",
                extra={
                    "event": "learning_decision_provider_failed",
                    "symbol": decision.symbol,
                    "error": str(exc),
                },
            )
            return None

    def _news_signal(self, decision: StrategyDecision) -> NewsSignal | None:
        if self._news_signal_provider is None:
            return None
        try:
            return self._news_signal_provider(decision)
        except Exception as exc:
            logger.warning(
                "news_signal_provider failed",
                extra={
                    "event": "news_signal_provider_failed",
                    "symbol": decision.symbol,
                    "error": str(exc),
                },
            )
            return None

    def handle_frame(self, frame: RuntimeFrame) -> RuntimeFrame | None:
        strategy_decision = frame.require_strategy_decision()

        learning_decision = self._learning_decision(strategy_decision)
        news_signal = self._news_signal(strategy_decision)

        started_at = time.perf_counter()
        try:
            final_decision = arbitrate(
                strategy_decision,
                learning_decision,
                news_signal,
                config=self._config,
                policy=self._policy,
            )
        except OrchestrationError as exc:
            self._metrics.counter(
                "final_decision_errors_total",
                "Number of arbitrate calls that raised.",
            ).inc()
            logger.warning(
                "final decision failed",
                extra={
                    "event": "final_decision_failed",
                    "symbol": strategy_decision.symbol,
                    "error": str(exc),
                },
            )
            return None
        latency_seconds = time.perf_counter() - started_at

        self._metrics.counter(
            "final_decisions_emitted_total",
            "Number of FinalDecisions successfully arbitrated and emitted.",
        ).inc()
        self._metrics.gauge(
            "final_decision_latency_seconds",
            "Latency of the most recent arbitrate call.",
        ).set(latency_seconds)

        logger.info(
            "final decision emitted",
            extra={
                "event": "final_decision_emitted",
                "symbol": final_decision.symbol,
                "timestamp": final_decision.timestamp.isoformat(),
                "outcome": final_decision.outcome.value,
                "primary_allocation": final_decision.primary_allocation,
                "final_allocation": final_decision.final_allocation,
                "confidence": final_decision.confidence,
                "latency_seconds": latency_seconds,
            },
        )

        return frame.with_final_decision(final_decision)


__all__ = ["LearningDecisionProvider", "NewsSignalProvider", "OrchestrationEmitter"]
