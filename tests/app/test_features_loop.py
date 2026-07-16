"""Tests for `app.features_loop.FeatureVectorEmitter`.

Uses the real `FeaturePipeline`/`DEFAULT_REGISTRY` for the success
path -- Phase B's job is to prove the wiring (buffer -> pipeline ->
log/metrics/callback) works, not to re-test feature computation itself
(covered by `tests/features/`). The failure path injects a fake
pipeline that always raises, since the real pipeline has no built-in
way to fail on valid, non-empty bar input.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from app.buffer import BarBuffer
from app.features_loop import FeatureVectorEmitter
from features.errors import FeatureComputationError
from features.feature_vector import FeatureVector
from features.pipeline import PIPELINE_VERSION
from market_data.models import Bar, CorporateAction, Timeframe

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bar(symbol: str = "AAPL", ts: datetime = T0, close: float = 100.0) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=ts,
        timeframe=Timeframe.DAY_1,
        open=close - 1,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
    )


class _RaisingPipeline:
    def compute(
        self,
        bars: Sequence[Bar],
        symbol: str,
        *,
        corporate_actions: Sequence[CorporateAction] = (),
        feature_names: Sequence[str] | None = None,
        source_dataset: str = "unspecified",
        strict: bool = False,
    ) -> FeatureVector:
        raise FeatureComputationError("simulated computation failure")


def _feature_vector_events(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, "event", None) == "feature_vector_computed"]


class TestFeatureVectorEmitter:
    def test_emits_feature_vector_and_logs_structured_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = FeatureVectorEmitter()
        with caplog.at_level(logging.INFO, logger="app.features_loop"):
            emitter.handle_bar(_bar())

        events = _feature_vector_events(caplog.records)
        assert len(events) == 1
        record = events[0]
        assert record.symbol == "AAPL"  # type: ignore[attr-defined]
        assert record.pipeline_version == PIPELINE_VERSION  # type: ignore[attr-defined]
        assert record.feature_count > 0  # type: ignore[attr-defined]
        assert record.latency_seconds >= 0.0  # type: ignore[attr-defined]

    def test_updates_metrics_on_success(self) -> None:
        emitter = FeatureVectorEmitter()
        emitter.handle_bar(_bar())

        assert emitter.metrics.counter("feature_vectors_emitted_total").value == 1.0
        assert emitter.metrics.gauge("feature_pipeline_latency_seconds").value >= 0.0

    def test_on_feature_vector_callback_is_called_with_the_computed_vector(self) -> None:
        received: list[FeatureVector] = []
        emitter = FeatureVectorEmitter(on_feature_vector=received.append)

        emitter.handle_bar(_bar())

        assert len(received) == 1
        assert received[0].symbol == "AAPL"

    def test_on_feature_vector_callback_failure_is_logged_and_does_not_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _boom(_vector: FeatureVector) -> None:
            raise RuntimeError("simulated callback failure")

        emitter = FeatureVectorEmitter(on_feature_vector=_boom)

        with caplog.at_level(logging.WARNING, logger="app.features_loop"):
            emitter.handle_bar(_bar())  # must not raise

        failures = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "on_feature_vector_callback_failed"
        ]
        assert len(failures) == 1

    def test_computation_failure_is_logged_and_does_not_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = FeatureVectorEmitter(
            buffer=BarBuffer(max_bars=10),
            pipeline=_RaisingPipeline(),  # type: ignore[arg-type]
        )

        with caplog.at_level(logging.WARNING, logger="app.features_loop"):
            emitter.handle_bar(_bar())  # must not raise

        failures = [
            r for r in caplog.records if getattr(r, "event", None) == "feature_computation_failed"
        ]
        assert len(failures) == 1
        assert emitter.metrics.counter("feature_computation_errors_total").value == 1.0
        assert _feature_vector_events(caplog.records) == []
