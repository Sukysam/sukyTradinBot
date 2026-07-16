"""`RegimeEmitter` -- Phase C: `FeatureVectorEmitter`'s `on_frame` hook
wired to `RegimeService`. See
docs/engineering-handbook/Architecture/ADR/ADR-029-Runtime-Regime-Detection-Design.md
and
docs/engineering-handbook/Architecture/ADR/ADR-030-Runtime-Strategy-Engine-Design.md.

`handle_frame` is the whole surface: append `frame.feature_vector` to a
bounded per-symbol `FeatureVectorBuffer`, call `RegimeService.infer`
on whatever history exists so far, log one structured event per
computed `RegimeState`, and record it on an `ops.metrics.MetricsRegistry`.
A failure is caught and logged, never propagated -- one bad inference
attempt (most commonly: not enough clean history yet, `hmm.exceptions.
InsufficientDataError`) must not stop the feature pipeline that fed it,
matching `FeatureVectorEmitter`'s own failure-isolation convention.
Self-heals once the buffer's bounded eviction has aged out every
NaN-flagged, still-warming-up vector -- no separate warm-up tracking
needed, the same reasoning `FeatureVectorEmitter` applies to
`FeaturePipeline.compute`'s own tolerance for partial history.
"""

from __future__ import annotations

import logging
import time

from app.buffer import FeatureVectorBuffer
from app.frame import RuntimeFrame, RuntimeFrameCallback
from hmm.exceptions import HMMError
from hmm.service import RegimeService
from ops.metrics import MetricsRegistry

logger = logging.getLogger(__name__)

# Comfortably above the largest registered feature lookback (100 bars),
# so a full buffer eventually evicts every still-warming-up vector --
# the same sizing rationale as `features_loop.DEFAULT_MAX_BARS`.
DEFAULT_MAX_FEATURE_VECTORS = 200


class RegimeEmitter:
    """Wraps exactly one `RegimeService`. `on_frame`, if given, is this
    class's own extension point for the next phase (Phase D: strategy)
    -- the same "each phase exposes one clean hook for the next" shape
    `MarketDataLoop.on_bar`/`FeatureVectorEmitter.on_frame` already
    established. Its failures are caught and logged, never propagated,
    for the same containment reason.
    """

    def __init__(
        self,
        regime_service: RegimeService,
        *,
        buffer: FeatureVectorBuffer | None = None,
        metrics: MetricsRegistry | None = None,
        on_frame: RuntimeFrameCallback | None = None,
    ) -> None:
        self._service = regime_service
        self._buffer = buffer or FeatureVectorBuffer(max_vectors=DEFAULT_MAX_FEATURE_VECTORS)
        self._metrics = metrics or MetricsRegistry()
        self._on_frame = on_frame

    @property
    def metrics(self) -> MetricsRegistry:
        return self._metrics

    def handle_frame(self, frame: RuntimeFrame) -> None:
        if frame.feature_vector is None:
            raise ValueError("RuntimeFrame reached RegimeEmitter without a feature_vector")
        vector = frame.feature_vector

        self._buffer.add(vector)
        history = self._buffer.get(vector.symbol)

        started_at = time.perf_counter()
        try:
            state = self._service.infer(history)
        except HMMError as exc:
            self._metrics.counter(
                "regime_inference_errors_total",
                "Number of RegimeService.infer calls that raised.",
            ).inc()
            logger.warning(
                "regime inference failed",
                extra={
                    "event": "regime_inference_failed",
                    "symbol": vector.symbol,
                    "error": str(exc),
                },
            )
            return
        latency_seconds = time.perf_counter() - started_at

        self._metrics.counter(
            "regime_states_emitted_total",
            "Number of RegimeStates successfully inferred and emitted.",
        ).inc()
        self._metrics.gauge(
            "regime_inference_latency_seconds",
            "Latency of the most recent RegimeService.infer call.",
        ).set(latency_seconds)

        logger.info(
            "regime state emitted",
            extra={
                "event": "regime_state_emitted",
                "symbol": state.symbol,
                "timestamp": state.timestamp.isoformat(),
                "regime_id": state.regime_id,
                "confidence": state.confidence,
                "transition_probability": state.transition_probability,
                "model_version": state.model_version,
                "latency_seconds": latency_seconds,
            },
        )

        if self._on_frame is not None:
            enriched = frame.with_regime_state(state)
            try:
                self._on_frame(enriched)
            except Exception as exc:
                logger.warning(
                    "on_frame callback failed",
                    extra={
                        "event": "on_frame_callback_failed",
                        "symbol": state.symbol,
                        "error": str(exc),
                    },
                )


__all__ = ["DEFAULT_MAX_FEATURE_VECTORS", "RegimeEmitter"]
