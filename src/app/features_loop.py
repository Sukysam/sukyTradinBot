"""`FeatureVectorEmitter` -- Phase B: `MarketDataLoop`'s `on_bar` hook
wired to `FeaturePipeline`. See
docs/engineering-handbook/Architecture/ADR/ADR-028-Runtime-Feature-Pipeline-Design.md.

`handle_bar` is the whole surface: append the bar to a bounded
per-symbol `BarBuffer`, call `FeaturePipeline.compute(strict=False)` on
whatever history exists so far, log one structured event per computed
`FeatureVector`, and record it on an `ops.metrics.MetricsRegistry`. A
computation failure is caught and logged, never propagated -- one bad
tick's feature computation must not stop the market-data loop that fed
it, matching `MarketDataLoop`'s own fetch-failure-isolation convention.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from app.buffer import BarBuffer
from features.errors import FeatureError
from features.feature_vector import FeatureVector
from features.pipeline import PIPELINE_VERSION, FeaturePipeline
from market_data.models import Bar
from ops.metrics import MetricsRegistry

logger = logging.getLogger(__name__)

FeatureVectorCallback = Callable[[FeatureVector], None]

# Comfortably above the largest registered feature lookback (100 bars,
# in features/statistical.py) so no feature is permanently starved of
# history -- see ADR-028's sizing rationale.
DEFAULT_MAX_BARS = 200


class FeatureVectorEmitter:
    """`on_feature_vector`, if given, is this class's own extension
    point for the next phase (Phase C: regime inference) -- the same
    "each phase exposes one clean hook for the next" shape as
    `MarketDataLoop.on_bar`. A callback failure is caught and logged,
    never propagated, for the same reason `MarketDataLoop`'s own
    `on_bar` dispatch is.
    """

    def __init__(
        self,
        *,
        buffer: BarBuffer | None = None,
        pipeline: FeaturePipeline | None = None,
        metrics: MetricsRegistry | None = None,
        on_feature_vector: FeatureVectorCallback | None = None,
    ) -> None:
        self._buffer = buffer or BarBuffer(max_bars=DEFAULT_MAX_BARS)
        self._pipeline = pipeline or FeaturePipeline()
        self._metrics = metrics or MetricsRegistry()
        self._on_feature_vector = on_feature_vector

    @property
    def metrics(self) -> MetricsRegistry:
        return self._metrics

    def handle_bar(self, bar: Bar) -> None:
        self._buffer.add(bar)
        bars = self._buffer.get(bar.symbol)

        started_at = time.perf_counter()
        try:
            vector = self._pipeline.compute(bars, bar.symbol, strict=False)
        except FeatureError as exc:
            self._metrics.counter(
                "feature_computation_errors_total",
                "Number of FeaturePipeline.compute calls that raised.",
            ).inc()
            logger.warning(
                "feature computation failed",
                extra={
                    "event": "feature_computation_failed",
                    "symbol": bar.symbol,
                    "error": str(exc),
                },
            )
            return
        latency_seconds = time.perf_counter() - started_at

        self._metrics.counter(
            "feature_vectors_emitted_total",
            "Number of FeatureVectors successfully computed and emitted.",
        ).inc()
        self._metrics.gauge(
            "feature_pipeline_latency_seconds",
            "Latency of the most recent FeaturePipeline.compute call.",
        ).set(latency_seconds)

        logger.info(
            "feature vector computed",
            extra={
                "event": "feature_vector_computed",
                "symbol": vector.symbol,
                "timestamp": vector.timestamp.isoformat(),
                "pipeline_version": PIPELINE_VERSION,
                "feature_count": len(vector.feature_names),
                "latency_seconds": latency_seconds,
            },
        )

        if self._on_feature_vector is not None:
            try:
                self._on_feature_vector(vector)
            except Exception as exc:
                logger.warning(
                    "on_feature_vector callback failed",
                    extra={
                        "event": "on_feature_vector_callback_failed",
                        "symbol": vector.symbol,
                        "error": str(exc),
                    },
                )


__all__ = ["DEFAULT_MAX_BARS", "FeatureVectorCallback", "FeatureVectorEmitter"]
