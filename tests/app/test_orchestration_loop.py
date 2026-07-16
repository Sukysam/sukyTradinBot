"""Tests for `app.orchestration_loop.OrchestrationEmitter`.

Uses the real `orchestration.arbitration.arbitrate`/`SafetyFirstPolicy`
(pure, deterministic, no I/O) for the success path -- Phase E's job is
to prove the wiring (frame -> arbitrate -> log/metrics) works, not to
re-test arbitration itself (covered by `tests/orchestration/`). No
`learning_decision_provider`/`news_signal_provider` is the default and
common case (mirrors running this runtime with no live Memory/NLP
wiring); tests separately confirm a supplied provider is consulted, a
raising provider degrades to "no advisory input" rather than failing
the frame, and a genuinely mismatched advisory signal (a real
`OrchestrationError` from `arbitrate` itself) is caught and logged.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.frame import RuntimeFrame
from app.orchestration_loop import OrchestrationEmitter
from features.feature_vector import FeatureVector, Provenance
from hmm.models import RegimeState
from market_data.models import Bar, Timeframe
from memory.models import LearningDecision
from nlp.models import NewsSignal
from strategy.models import StrategyDecision

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


def _regime_state() -> RegimeState:
    return RegimeState(
        timestamp=T0,
        symbol=SYMBOL,
        regime_id=0,
        confidence=0.8,
        transition_probability=0.9,
        model_version="v1",
        feature_pipeline_version="2",
        metadata={},
    )


def _strategy_decision() -> StrategyDecision:
    return StrategyDecision(
        timestamp=T0,
        symbol=SYMBOL,
        strategy_id="growth",
        regime_id=0,
        allocation=0.5,
        confidence=0.8,
        expected_holding_period=timedelta(days=20),
        reasoning="test",
        metadata={},
    )


def _frame() -> RuntimeFrame:
    return RuntimeFrame(
        bar=_bar(),
        feature_vector=_feature_vector(),
        regime_state=_regime_state(),
        strategy_decision=_strategy_decision(),
    )


def _matching_learning_decision() -> LearningDecision:
    return LearningDecision(
        timestamp=T0,
        symbol=SYMBOL,
        strategy_id="growth",
        regime_id=0,
        production_allocation=0.5,
        recommended_allocation=0.5,
        confidence=0.8,
        sample_size=10,
        rationale="test",
        model_version="v1",
        metadata={},
    )


def _mismatched_learning_decision() -> LearningDecision:
    return LearningDecision(
        timestamp=T0,
        symbol="MSFT",  # deliberately wrong symbol -- triggers MismatchedSignalError
        strategy_id="growth",
        regime_id=0,
        production_allocation=0.5,
        recommended_allocation=0.5,
        confidence=0.8,
        sample_size=10,
        rationale="test",
        model_version="v1",
        metadata={},
    )


def _final_decision_events(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, "event", None) == "final_decision_emitted"]


class TestOrchestrationEmitter:
    def test_emits_final_decision_and_logs_structured_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = OrchestrationEmitter()
        with caplog.at_level(logging.INFO, logger="app.orchestration_loop"):
            emitter.handle_frame(_frame())

        events = _final_decision_events(caplog.records)
        assert len(events) == 1
        record = events[0]
        assert record.symbol == SYMBOL  # type: ignore[attr-defined]
        assert record.primary_allocation == 0.5  # type: ignore[attr-defined]
        assert record.latency_seconds >= 0.0  # type: ignore[attr-defined]

    def test_updates_metrics_on_success(self) -> None:
        emitter = OrchestrationEmitter()
        emitter.handle_frame(_frame())

        assert emitter.metrics.counter("final_decisions_emitted_total").value == 1.0
        assert emitter.metrics.gauge("final_decision_latency_seconds").value >= 0.0

    def test_handle_frame_returns_a_frame_carrying_the_final_decision(self) -> None:
        emitter = OrchestrationEmitter()

        frame = emitter.handle_frame(_frame())

        assert frame is not None
        assert frame.final_decision is not None
        assert frame.final_decision.symbol == SYMBOL
        assert frame.strategy_decision is not None

    def test_no_providers_means_no_advisory_input(self) -> None:
        emitter = OrchestrationEmitter()

        frame = emitter.handle_frame(_frame())

        assert frame is not None
        assert frame.final_decision is not None
        assert frame.final_decision.learner_input.considered is False
        assert frame.final_decision.news_input.considered is False

    def test_supplied_learning_decision_provider_is_consulted(self) -> None:
        emitter = OrchestrationEmitter(
            learning_decision_provider=lambda _decision: _matching_learning_decision()
        )

        frame = emitter.handle_frame(_frame())

        assert frame is not None
        assert frame.final_decision is not None
        assert frame.final_decision.learner_input.considered is True

    def test_provider_failure_is_logged_and_treated_as_no_advisory_input(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _boom(_decision: StrategyDecision) -> LearningDecision:
            raise RuntimeError("simulated provider failure")

        emitter = OrchestrationEmitter(learning_decision_provider=_boom)

        with caplog.at_level(logging.WARNING, logger="app.orchestration_loop"):
            frame = emitter.handle_frame(_frame())  # must not raise

        assert frame is not None
        assert frame.final_decision is not None
        assert frame.final_decision.learner_input.considered is False
        failures = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "learning_decision_provider_failed"
        ]
        assert len(failures) == 1

    def test_news_signal_provider_failure_is_logged_and_treated_as_no_advisory_input(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _boom(_decision: StrategyDecision) -> NewsSignal:
            raise RuntimeError("simulated provider failure")

        emitter = OrchestrationEmitter(news_signal_provider=_boom)

        with caplog.at_level(logging.WARNING, logger="app.orchestration_loop"):
            frame = emitter.handle_frame(_frame())  # must not raise

        assert frame is not None
        assert frame.final_decision is not None
        assert frame.final_decision.news_input.considered is False
        failures = [
            r for r in caplog.records if getattr(r, "event", None) == "news_signal_provider_failed"
        ]
        assert len(failures) == 1

    def test_arbitration_failure_is_logged_and_returns_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = OrchestrationEmitter(
            learning_decision_provider=lambda _decision: _mismatched_learning_decision()
        )

        with caplog.at_level(logging.WARNING, logger="app.orchestration_loop"):
            frame = emitter.handle_frame(_frame())  # must not raise

        assert frame is None
        failures = [
            r for r in caplog.records if getattr(r, "event", None) == "final_decision_failed"
        ]
        assert len(failures) == 1
        assert emitter.metrics.counter("final_decision_errors_total").value == 1.0
        assert _final_decision_events(caplog.records) == []

    def test_raises_when_frame_missing_strategy_decision(self) -> None:
        emitter = OrchestrationEmitter()
        with pytest.raises(ValueError, match="strategy_decision"):
            emitter.handle_frame(
                RuntimeFrame(
                    bar=_bar(), feature_vector=_feature_vector(), regime_state=_regime_state()
                )
            )
