"""`StrategyEmitter` -- Phase D: the stage after `RegimeEmitter` in the
composed pipeline, wired to `StrategyService`. See
docs/engineering-handbook/Architecture/ADR/ADR-030-Runtime-Strategy-Engine-Design.md
and
docs/engineering-handbook/Architecture/ADR/ADR-031-Signal-Orchestration-Design.md.

`handle_frame` is the whole surface: call `StrategyService.decide` with
`frame.feature_vector`/`frame.regime_state` (both already present on
the frame by the time it reaches this class -- `RuntimeFrame`'s own
enrichment-order invariant guarantees it), log one structured event
per computed `StrategyDecision`, record it on an `ops.metrics.
MetricsRegistry`, and return the enriched frame -- or `None` on
failure. A failure is caught and logged, never propagated, matching
`RegimeEmitter`'s own failure-isolation convention. No buffer here --
unlike `FeaturePipeline.compute`/`RegimeService.infer`,
`StrategyService.decide` needs only the current `(FeatureVector,
RegimeState)` pair, no rolling history.
"""

from __future__ import annotations

import logging
import time

from app.frame import RuntimeFrame
from ops.metrics import MetricsRegistry
from strategy.exceptions import StrategyError
from strategy.service import StrategyService

logger = logging.getLogger(__name__)


class StrategyEmitter:
    """Wraps exactly one `StrategyService`. Holds no "next stage" hook
    -- see `app.pipeline.compose_pipeline` for how this is wired to
    whatever comes after it.
    """

    def __init__(
        self,
        strategy_service: StrategyService,
        *,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._service = strategy_service
        self._metrics = metrics or MetricsRegistry()

    @property
    def metrics(self) -> MetricsRegistry:
        return self._metrics

    def handle_frame(self, frame: RuntimeFrame) -> RuntimeFrame | None:
        if frame.feature_vector is None or frame.regime_state is None:
            raise ValueError(
                "RuntimeFrame reached StrategyEmitter without a feature_vector/regime_state"
            )
        feature_vector, regime_state = frame.feature_vector, frame.regime_state

        started_at = time.perf_counter()
        try:
            decision = self._service.decide(feature_vector, regime_state)
        except StrategyError as exc:
            self._metrics.counter(
                "strategy_decision_errors_total",
                "Number of StrategyService.decide calls that raised.",
            ).inc()
            logger.warning(
                "strategy decision failed",
                extra={
                    "event": "strategy_decision_failed",
                    "symbol": feature_vector.symbol,
                    "error": str(exc),
                },
            )
            return None
        latency_seconds = time.perf_counter() - started_at

        self._metrics.counter(
            "strategy_decisions_emitted_total",
            "Number of StrategyDecisions successfully computed and emitted.",
        ).inc()
        self._metrics.gauge(
            "strategy_decision_latency_seconds",
            "Latency of the most recent StrategyService.decide call.",
        ).set(latency_seconds)

        logger.info(
            "strategy decision emitted",
            extra={
                "event": "strategy_decision_emitted",
                "symbol": decision.symbol,
                "timestamp": decision.timestamp.isoformat(),
                "strategy_id": decision.strategy_id,
                "regime_id": decision.regime_id,
                "allocation": decision.allocation,
                "confidence": decision.confidence,
                "latency_seconds": latency_seconds,
            },
        )

        return frame.with_strategy_decision(decision)


__all__ = ["StrategyEmitter"]
