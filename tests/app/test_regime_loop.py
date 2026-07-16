"""Tests for `app.regime_loop.RegimeEmitter`.

Uses a real, cheaply-trained `RegimeService` (same "small config, few
candidate states" pattern as `tests/hmm/test_service.py`) for the
success path -- Phase C's job is to prove the wiring (buffer ->
RegimeService.infer -> log/metrics/callback) works, not to re-test
regime inference itself (covered by `tests/hmm/`). The failure path
injects a fake service, since a well-formed real service has no simple
way to fail on valid history it's been trained to accept.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np
import pytest

from app.buffer import FeatureVectorBuffer
from app.frame import RuntimeFrame
from app.regime_loop import RegimeEmitter
from features.feature_vector import FeatureVector
from hmm.config import HMMConfig, SelectionConfig, TrainingConfig
from hmm.exceptions import InsufficientDataError
from hmm.models import RegimeState
from hmm.service import RegimeService
from market_data.models import Bar, Timeframe
from tests.hmm.conftest import make_feature_vectors, synthetic_regime_matrix

FEATURE_NAMES = ("f1", "f2")
SYMBOL = "TEST"


def _fast_config() -> HMMConfig:
    return HMMConfig(
        selection=SelectionConfig(candidate_states=(2, 3)),
        training=TrainingConfig(n_init=2, n_iter=50, random_state=1),
    )


def _trained_service() -> RegimeService:
    rng = np.random.default_rng(7)
    X = synthetic_regime_matrix(rng, regime_means=[(0.0, 0.0), (6.0, -6.0)], n_per_regime=60)
    history = make_feature_vectors(X, FEATURE_NAMES, symbol=SYMBOL)
    return RegimeService.train(history, symbol=SYMBOL, model_version="v1", config=_fast_config())


def _live_frame(value: tuple[float, float] = (0.0, 0.0)) -> RuntimeFrame:
    X = np.array([value])
    vector = make_feature_vectors(X, FEATURE_NAMES, symbol=SYMBOL)[0]
    bar = Bar(
        symbol=SYMBOL,
        timestamp=vector.timestamp,
        timeframe=Timeframe.DAY_1,
        open=99.0,
        high=101.0,
        low=98.0,
        close=100.0,
        volume=1000.0,
    )
    return RuntimeFrame(bar=bar, feature_vector=vector)


class _RaisingService:
    n_states = 2

    def infer(self, history: Sequence[FeatureVector]) -> RegimeState:
        raise InsufficientDataError("simulated inference failure")


def _regime_state_events(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, "event", None) == "regime_state_emitted"]


class TestRegimeEmitter:
    def test_emits_regime_state_and_logs_structured_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = RegimeEmitter(_trained_service())
        with caplog.at_level(logging.INFO, logger="app.regime_loop"):
            emitter.handle_frame(_live_frame())

        events = _regime_state_events(caplog.records)
        assert len(events) == 1
        record = events[0]
        assert record.symbol == SYMBOL  # type: ignore[attr-defined]
        assert record.model_version == "v1"  # type: ignore[attr-defined]
        assert record.regime_id >= 0  # type: ignore[attr-defined]
        assert 0.0 <= record.confidence <= 1.0  # type: ignore[attr-defined]
        assert record.latency_seconds >= 0.0  # type: ignore[attr-defined]

    def test_updates_metrics_on_success(self) -> None:
        emitter = RegimeEmitter(_trained_service())
        emitter.handle_frame(_live_frame())

        assert emitter.metrics.counter("regime_states_emitted_total").value == 1.0
        assert emitter.metrics.gauge("regime_inference_latency_seconds").value >= 0.0

    def test_handle_frame_returns_a_frame_carrying_the_regime_state(self) -> None:
        emitter = RegimeEmitter(_trained_service())

        frame = emitter.handle_frame(_live_frame())

        assert frame is not None
        assert frame.regime_state is not None
        assert frame.regime_state.symbol == SYMBOL
        assert frame.feature_vector is not None

    def test_inference_failure_is_logged_and_returns_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = RegimeEmitter(
            _RaisingService(),  # type: ignore[arg-type]
            buffer=FeatureVectorBuffer(max_vectors=10),
        )

        with caplog.at_level(logging.WARNING, logger="app.regime_loop"):
            frame = emitter.handle_frame(_live_frame())  # must not raise

        assert frame is None
        failures = [
            r for r in caplog.records if getattr(r, "event", None) == "regime_inference_failed"
        ]
        assert len(failures) == 1
        assert emitter.metrics.counter("regime_inference_errors_total").value == 1.0
        assert _regime_state_events(caplog.records) == []

    def test_raises_when_frame_has_no_feature_vector(self) -> None:
        bar = Bar(
            symbol=SYMBOL,
            timestamp=make_feature_vectors(np.array([[0.0, 0.0]]), FEATURE_NAMES)[0].timestamp,
            timeframe=Timeframe.DAY_1,
            open=99.0,
            high=101.0,
            low=98.0,
            close=100.0,
            volume=1000.0,
        )
        emitter = RegimeEmitter(_trained_service())
        with pytest.raises(ValueError, match="feature_vector"):
            emitter.handle_frame(RuntimeFrame(bar=bar))
