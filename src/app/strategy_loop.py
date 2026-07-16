"""`StrategyEmitter` -- Phase D: `RegimeEmitter`'s `on_frame` hook wired
to `StrategyService`. See
docs/engineering-handbook/Architecture/ADR/ADR-030-Runtime-Strategy-Engine-Design.md.

`handle_frame` is the whole surface: call `StrategyService.decide` with
`frame.feature_vector`/`frame.regime_state` (both already present on
the frame by the time it reaches this class -- `RuntimeFrame`'s own
enrichment-order invariant guarantees it), log one structured event
per computed `StrategyDecision`, and record it on an `ops.metrics.
MetricsRegistry`. A failure is caught and logged, never propagated,
matching `RegimeEmitter`'s own failure-isolation convention. No buffer
here -- unlike `FeaturePipeline.compute`/`RegimeService.infer`,
`StrategyService.decide` needs only the current `(FeatureVector,
RegimeState)` pair, no rolling history.
"""

from __future__ import annotations

import logging
import time

from app.frame import RuntimeFrame, RuntimeFrameCallback
from ops.metrics import MetricsRegistry
from strategy.exceptions import StrategyError
from strategy.service import StrategyService

logger = logging.getLogger(__name__)


class StrategyEmitter:
    """Wraps exactly one `StrategyService`. `on_frame`, if given, is
    this class's own extension point for the next phase (Phase E:
    signal orchestration) -- the same "each phase exposes one clean
    hook for the next" shape every earlier emitter in `app` already
    established. Its failures are caught and logged, never propagated,
    for the same containment reason.
    """

    def __init__(
        self,
        strategy_service: StrategyService,
        *,
        metrics: MetricsRegistry | None = None,
        on_frame: RuntimeFrameCallback | None = None,
    ) -> None:
        self._service = strategy_service
        self._metrics = metrics or MetricsRegistry()
        self._on_frame = on_frame

    @property
    def metrics(self) -> MetricsRegistry:
        return self._metrics

    def handle_frame(self, frame: RuntimeFrame) -> None:
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
            return
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

        if self._on_frame is not None:
            enriched = frame.with_strategy_decision(decision)
            try:
                self._on_frame(enriched)
            except Exception as exc:
                logger.warning(
                    "on_frame callback failed",
                    extra={
                        "event": "on_frame_callback_failed",
                        "symbol": decision.symbol,
                        "error": str(exc),
                    },
                )


__all__ = ["StrategyEmitter"]
