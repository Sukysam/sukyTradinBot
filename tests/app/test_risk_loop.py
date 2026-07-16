"""Tests for `app.risk_loop.RiskEmitter`.

Uses a real `RiskService.default()` (cheap -- no training, no I/O) for
the success path -- Phase F's job is to prove the wiring (frame ->
RiskService.decide -> log/metrics) and the `FinalDecision ->
StrategyDecision` bridge work, not to re-test risk sizing itself
(covered by `tests/risk/`). The failure path injects a fake service,
since `RiskService.decide` only raises for a `SizingRule` bug (not a
normal validator rejection, which just produces `approved=False`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.frame import RuntimeFrame
from app.risk_loop import RiskEmitter
from features.feature_vector import FeatureVector, Provenance
from hmm.models import RegimeState
from market_data.models import Bar, Timeframe
from orchestration.models import ArbitrationOutcome, FinalDecision, SignalInput
from risk.exceptions import InvalidSizingResultError
from risk.models import AccountState, ExecutionDecision, PortfolioState
from risk.service import RiskService
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


def _strategy_decision(allocation: float = 0.8) -> StrategyDecision:
    return StrategyDecision(
        timestamp=T0,
        symbol=SYMBOL,
        strategy_id="growth",
        regime_id=0,
        allocation=allocation,
        confidence=0.8,
        expected_holding_period=timedelta(days=20),
        reasoning="test",
        metadata={},
    )


def _final_decision(final_allocation: float = 0.5) -> FinalDecision:
    absent = SignalInput(source="memory", considered=False, agrees=False, weight=0.0)
    outcome = (
        ArbitrationOutcome.CONFIRMED if final_allocation == 0.8 else ArbitrationOutcome.ADJUSTED
    )
    return FinalDecision(
        timestamp=T0,
        symbol=SYMBOL,
        strategy_id="growth",
        regime_id=0,
        primary_allocation=0.8,
        final_allocation=final_allocation,
        confidence=0.7,
        outcome=outcome,
        learner_input=absent,
        news_input=SignalInput(source="nlp", considered=False, agrees=False, weight=0.0),
        rationale="arbitrated for test",
        metadata={},
    )


def _frame(final_allocation: float = 0.5) -> RuntimeFrame:
    return RuntimeFrame(
        bar=_bar(),
        feature_vector=_feature_vector(),
        regime_state=_regime_state(),
        strategy_decision=_strategy_decision(),
        final_decision=_final_decision(final_allocation),
    )


def _portfolio_state() -> PortfolioState:
    return PortfolioState(
        equity=100_000.0,
        positions=(),
        equity_start_of_day=100_000.0,
        equity_start_of_week=100_000.0,
        equity_peak=100_000.0,
    )


def _account_state() -> AccountState:
    return AccountState(buying_power=100_000.0)


class _RaisingRiskService:
    def decide(
        self, decision: StrategyDecision, portfolio: PortfolioState, account: AccountState
    ) -> ExecutionDecision:
        raise InvalidSizingResultError("simulated risk failure")


def _execution_decision_events(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, "event", None) == "execution_decision_emitted"]


class TestRiskEmitter:
    def test_emits_execution_decision_and_logs_structured_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = RiskEmitter(RiskService.default(), _portfolio_state, _account_state)
        with caplog.at_level(logging.INFO, logger="app.risk_loop"):
            emitter.handle_frame(_frame())

        events = _execution_decision_events(caplog.records)
        assert len(events) == 1
        record = events[0]
        assert record.symbol == SYMBOL  # type: ignore[attr-defined]
        assert record.approved is True  # type: ignore[attr-defined]
        assert record.latency_seconds >= 0.0  # type: ignore[attr-defined]

    def test_sizes_against_the_arbitrated_allocation_not_the_original(self) -> None:
        # strategy_decision.allocation is 0.8, but final_decision.final_allocation
        # is 0.5 -- approved_allocation must never exceed the arbitrated ceiling.
        emitter = RiskEmitter(RiskService.default(), _portfolio_state, _account_state)

        frame = emitter.handle_frame(_frame(final_allocation=0.5))

        assert frame is not None
        assert frame.execution_decision is not None
        assert frame.execution_decision.approved_allocation <= 0.5

    def test_updates_metrics_on_success(self) -> None:
        emitter = RiskEmitter(RiskService.default(), _portfolio_state, _account_state)
        emitter.handle_frame(_frame())

        assert emitter.metrics.counter("execution_decisions_emitted_total").value == 1.0
        assert emitter.metrics.gauge("execution_decision_latency_seconds").value >= 0.0

    def test_handle_frame_returns_a_frame_carrying_the_execution_decision(self) -> None:
        emitter = RiskEmitter(RiskService.default(), _portfolio_state, _account_state)

        frame = emitter.handle_frame(_frame())

        assert frame is not None
        assert frame.execution_decision is not None
        assert frame.execution_decision.symbol == SYMBOL
        assert frame.final_decision is not None

    def test_decision_failure_is_logged_and_returns_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = RiskEmitter(
            _RaisingRiskService(), _portfolio_state, _account_state  # type: ignore[arg-type]
        )

        with caplog.at_level(logging.WARNING, logger="app.risk_loop"):
            frame = emitter.handle_frame(_frame())  # must not raise

        assert frame is None
        failures = [
            r for r in caplog.records if getattr(r, "event", None) == "execution_decision_failed"
        ]
        assert len(failures) == 1
        assert emitter.metrics.counter("execution_decision_errors_total").value == 1.0
        assert _execution_decision_events(caplog.records) == []

    def test_portfolio_state_provider_failure_is_logged_and_returns_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _boom() -> PortfolioState:
            raise RuntimeError("simulated provider failure")

        emitter = RiskEmitter(RiskService.default(), _boom, _account_state)

        with caplog.at_level(logging.WARNING, logger="app.risk_loop"):
            frame = emitter.handle_frame(_frame())  # must not raise

        assert frame is None
        failures = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "portfolio_state_provider_failed"
        ]
        assert len(failures) == 1
        assert emitter.metrics.counter("execution_decision_errors_total").value == 1.0

    def test_account_state_provider_failure_is_logged_and_returns_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _boom() -> AccountState:
            raise RuntimeError("simulated provider failure")

        emitter = RiskEmitter(RiskService.default(), _portfolio_state, _boom)

        with caplog.at_level(logging.WARNING, logger="app.risk_loop"):
            frame = emitter.handle_frame(_frame())  # must not raise

        assert frame is None
        failures = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "account_state_provider_failed"
        ]
        assert len(failures) == 1
        assert emitter.metrics.counter("execution_decision_errors_total").value == 1.0

    def test_raises_when_frame_missing_strategy_decision(self) -> None:
        emitter = RiskEmitter(RiskService.default(), _portfolio_state, _account_state)
        with pytest.raises(ValueError, match="strategy_decision"):
            emitter.handle_frame(RuntimeFrame(bar=_bar()))

    def test_raises_when_frame_missing_final_decision(self) -> None:
        emitter = RiskEmitter(RiskService.default(), _portfolio_state, _account_state)
        with pytest.raises(ValueError, match="final_decision"):
            emitter.handle_frame(
                RuntimeFrame(
                    bar=_bar(),
                    feature_vector=_feature_vector(),
                    regime_state=_regime_state(),
                    strategy_decision=_strategy_decision(),
                )
            )
