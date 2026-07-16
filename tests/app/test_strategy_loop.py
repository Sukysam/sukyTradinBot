"""Tests for `app.strategy_loop.StrategyEmitter`.

Uses a real `StrategyService`/`StrategyRegistry` (cheap -- no training,
no I/O, unlike `hmm.service.RegimeService`) for the success path --
Phase D's job is to prove the wiring (frame -> StrategyService.decide
-> log/metrics/callback) works, not to re-test strategy allocation
itself (covered by `tests/strategy/`). The failure path injects a fake
service, since a well-formed real service has no simple way to fail on
a regime_id it's configured to support.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from app.frame import RuntimeFrame
from app.strategy_loop import StrategyEmitter
from features.feature_vector import FeatureVector, Provenance
from hmm.models import RegimeState
from market_data.models import Bar, Timeframe
from strategy.exceptions import UnsupportedRegimeError
from strategy.models import StrategyDecision
from strategy.registry import StrategyRegistry
from strategy.service import StrategyService
from strategy.strategies import create_growth_strategy

UTC = timezone.utc
SYMBOL = "AAPL"
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bar() -> Bar:
    return Bar(
        symbol=SYMBOL,
        timestamp=T0,
        timeframe=Timeframe.DAY_1,
        open=99.0,
        high=101.0,
        low=98.0,
        close=100.0,
        volume=1000.0,
    )


def _feature_vector() -> FeatureVector:
    return FeatureVector(
        timestamp=T0,
        symbol=SYMBOL,
        feature_values=(1.0,),
        feature_names=("f1",),
        metadata={},
        quality_flags={},
        provenance=Provenance(
            pipeline_version="2",
            manifest_version="1",
            feature_versions={"f1": 1},
            generated_at=T0,
            source_dataset="test",
        ),
    )


def _regime_state(regime_id: int = 0) -> RegimeState:
    return RegimeState(
        timestamp=T0,
        symbol=SYMBOL,
        regime_id=regime_id,
        confidence=0.8,
        transition_probability=0.9,
        model_version="v1",
        feature_pipeline_version="2",
        metadata={},
    )


def _frame(regime_id: int = 0) -> RuntimeFrame:
    return RuntimeFrame(
        bar=_bar(), feature_vector=_feature_vector(), regime_state=_regime_state(regime_id)
    )


def _real_service() -> StrategyService:
    registry = StrategyRegistry()
    registry.register(create_growth_strategy("growth", frozenset({0})))
    return StrategyService(registry)


class _RaisingService:
    def decide(self, feature_vector: FeatureVector, regime_state: RegimeState) -> StrategyDecision:
        raise UnsupportedRegimeError("simulated dispatch failure")


def _strategy_decision_events(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, "event", None) == "strategy_decision_emitted"]


class TestStrategyEmitter:
    def test_emits_strategy_decision_and_logs_structured_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = StrategyEmitter(_real_service())
        with caplog.at_level(logging.INFO, logger="app.strategy_loop"):
            emitter.handle_frame(_frame())

        events = _strategy_decision_events(caplog.records)
        assert len(events) == 1
        record = events[0]
        assert record.symbol == SYMBOL  # type: ignore[attr-defined]
        assert record.strategy_id == "growth"  # type: ignore[attr-defined]
        assert record.regime_id == 0  # type: ignore[attr-defined]
        assert 0.0 <= record.allocation <= 1.0  # type: ignore[attr-defined]
        assert record.latency_seconds >= 0.0  # type: ignore[attr-defined]

    def test_updates_metrics_on_success(self) -> None:
        emitter = StrategyEmitter(_real_service())
        emitter.handle_frame(_frame())

        assert emitter.metrics.counter("strategy_decisions_emitted_total").value == 1.0
        assert emitter.metrics.gauge("strategy_decision_latency_seconds").value >= 0.0

    def test_handle_frame_returns_a_frame_carrying_the_decision(self) -> None:
        emitter = StrategyEmitter(_real_service())

        frame = emitter.handle_frame(_frame())

        assert frame is not None
        assert frame.strategy_decision is not None
        assert frame.strategy_decision.strategy_id == "growth"
        assert frame.regime_state is not None

    def test_decision_failure_is_logged_and_returns_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = StrategyEmitter(_RaisingService())  # type: ignore[arg-type]

        with caplog.at_level(logging.WARNING, logger="app.strategy_loop"):
            frame = emitter.handle_frame(_frame())  # must not raise

        assert frame is None
        failures = [
            r for r in caplog.records if getattr(r, "event", None) == "strategy_decision_failed"
        ]
        assert len(failures) == 1
        assert emitter.metrics.counter("strategy_decision_errors_total").value == 1.0
        assert _strategy_decision_events(caplog.records) == []

    def test_raises_when_frame_missing_feature_vector(self) -> None:
        emitter = StrategyEmitter(_real_service())
        with pytest.raises(ValueError, match="feature_vector"):
            emitter.handle_frame(RuntimeFrame(bar=_bar()))

    def test_raises_when_frame_missing_regime_state(self) -> None:
        emitter = StrategyEmitter(_real_service())
        with pytest.raises(ValueError, match="regime_state"):
            emitter.handle_frame(RuntimeFrame(bar=_bar(), feature_vector=_feature_vector()))
