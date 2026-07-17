"""Tests for `app.execution_loop.ExecutionEmitter` and
`app.execution_loop.BrokerSubmissionEmitter`.

`ExecutionEmitter` is exercised with a real `ExecutionService` wired to
fake, in-memory market/feature snapshot providers (mirroring
`tests/execution/test_execution_service.py`'s own convention) -- no
network, no Alpaca. `BrokerSubmissionEmitter` is exercised with a
`unittest.mock.MagicMock` standing in for `BrokerAdapter` (mirroring
`tests/execution/test_retry.py`'s own convention) -- this test suite
never constructs a real `AlpacaBrokerAdapter` or `TradingClient`, and
never invokes real order submission.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.execution_loop import BrokerSubmissionEmitter, ExecutionEmitter
from app.frame import RuntimeFrame
from common.retry import RetryPolicy
from execution.broker_adapter import BrokerSubmissionResult
from execution.exceptions import ExecutionError, TransientBrokerError
from execution.execution_service import ExecutionService
from execution.models import (
    ExecutionContext,
    FeatureSnapshot,
    OrderIntent,
    OrderSide,
    OrderType,
    TimeInForce,
)
from execution.order_builder import OrderBuilder
from execution.stop_loss import ATRStopPolicy
from features.feature_vector import FeatureVector, Provenance
from hmm.models import RegimeState
from market_data.models import Bar, Timeframe
from orchestration.models import ArbitrationOutcome, FinalDecision, SignalInput
from risk.models import DecisionType, ExecutionDecision, PortfolioState
from strategy.models import StrategyDecision

UTC = timezone.utc
SYMBOL = "AAPL"
T0 = datetime(2024, 1, 1, tzinfo=UTC)

_NO_SLEEP_POLICY = RetryPolicy(max_attempts=3, initial_delay_seconds=0.0, backoff_multiplier=1.0)
# Mirrors DEFAULT_BROKER_RETRY_POLICY's own `exceptions` filter (only
# TransientBrokerError is retried) but with no sleep -- needed to prove
# a genuinely unexpected exception (anything else) is never retried and
# propagates out of submit_with_retry for BrokerSubmissionEmitter's own
# try/except to catch.
_NO_SLEEP_TRANSIENT_ONLY_POLICY = RetryPolicy(
    max_attempts=3,
    initial_delay_seconds=0.0,
    backoff_multiplier=1.0,
    exceptions=(TransientBrokerError,),
)


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


def _strategy_decision(allocation: float = 0.5) -> StrategyDecision:
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
    return FinalDecision(
        timestamp=T0,
        symbol=SYMBOL,
        strategy_id="growth",
        regime_id=0,
        primary_allocation=0.5,
        final_allocation=final_allocation,
        confidence=0.8,
        outcome=ArbitrationOutcome.CONFIRMED,
        learner_input=absent,
        news_input=SignalInput(source="nlp", considered=False, agrees=False, weight=0.0),
        rationale="test",
        metadata={},
    )


def _execution_decision(
    *, approved: bool = True, approved_allocation: float = 0.5
) -> ExecutionDecision:
    strategy_decision = _strategy_decision()
    if not approved:
        return ExecutionDecision(
            timestamp=T0,
            symbol=SYMBOL,
            approved=False,
            approved_allocation=0.0,
            decision_type=DecisionType.REJECTED,
            risk_adjustments=("test: rejected",),
            reasoning="Rejected: test",
            strategy_reference=strategy_decision,
            metadata={},
        )
    return ExecutionDecision(
        timestamp=T0,
        symbol=SYMBOL,
        approved=True,
        approved_allocation=approved_allocation,
        decision_type=DecisionType.APPROVED,
        risk_adjustments=(),
        reasoning="Approved at full size; no limits binding.",
        strategy_reference=strategy_decision,
        metadata={},
    )


def _frame(
    *, approved: bool = True, execution_decision: ExecutionDecision | None = None
) -> RuntimeFrame:
    return RuntimeFrame(
        bar=_bar(),
        feature_vector=_feature_vector(),
        regime_state=_regime_state(),
        strategy_decision=_strategy_decision(),
        final_decision=_final_decision(),
        execution_decision=execution_decision or _execution_decision(approved=approved),
    )


def _order_intent_frame() -> RuntimeFrame:
    """A frame enriched all the way to `order_intent`, for
    `BrokerSubmissionEmitter` tests."""
    decision = _execution_decision()
    intent = OrderIntent(
        timestamp=T0,
        symbol=SYMBOL,
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.MARKET,
        limit_price=None,
        time_in_force=TimeInForce.DAY,
        reference_price=100.0,
        stop_loss=95.0,
        take_profit=None,
        idempotency_key="key-1",
        reasoning="test reasoning",
        execution_reference=decision,
        metadata={},
    )
    return _frame(execution_decision=decision).with_order_intent(intent)


def _portfolio_state(*, equity: float = 100_000.0) -> PortfolioState:
    return PortfolioState(
        equity=equity,
        positions=(),
        equity_start_of_day=equity,
        equity_start_of_week=equity,
        equity_peak=equity,
    )


@dataclass(frozen=True)
class _FakeMarketSnapshotProvider:
    context: ExecutionContext

    def get_snapshot(self, symbol: str) -> ExecutionContext:
        assert symbol == self.context.symbol
        return self.context


@dataclass(frozen=True)
class _FakeFeatureSnapshotProvider:
    snapshot: FeatureSnapshot

    def get_latest(self, symbol: str) -> FeatureSnapshot:
        assert symbol == self.snapshot.symbol
        return self.snapshot


def _execution_service() -> ExecutionService:
    market_provider = _FakeMarketSnapshotProvider(
        ExecutionContext(
            symbol=SYMBOL,
            timestamp=T0,
            reference_price=100.0,
            bid=None,
            ask=None,
            spread=None,
            tick_size=0.01,
            price_source="bar_close",
        )
    )
    feature_provider = _FakeFeatureSnapshotProvider(
        FeatureSnapshot(symbol=SYMBOL, timestamp=T0, atr_14=2.0, realized_volatility_20=0.02)
    )
    return ExecutionService(
        market_snapshot_provider=market_provider,
        feature_snapshot_provider=feature_provider,
        order_builder=OrderBuilder(stop_loss_policy=ATRStopPolicy(atr_multiplier=2.0)),
    )


class _RaisingExecutionService:
    def decide(
        self, execution_decision: ExecutionDecision, portfolio: PortfolioState
    ) -> OrderIntent | None:
        raise ExecutionError("simulated execution failure")


def _order_intent_events(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, "event", None) == "order_intent_emitted"]


class TestExecutionEmitter:
    def test_emits_order_intent_and_logs_structured_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = ExecutionEmitter(_execution_service(), _portfolio_state)
        with caplog.at_level(logging.INFO, logger="app.execution_loop"):
            emitter.handle_frame(_frame())

        events = _order_intent_events(caplog.records)
        assert len(events) == 1
        record = events[0]
        assert record.symbol == SYMBOL  # type: ignore[attr-defined]
        assert record.side == "buy"  # type: ignore[attr-defined]
        assert record.latency_seconds >= 0.0  # type: ignore[attr-defined]

    def test_handle_frame_returns_a_frame_carrying_the_order_intent(self) -> None:
        emitter = ExecutionEmitter(_execution_service(), _portfolio_state)

        frame = emitter.handle_frame(_frame())

        assert frame is not None
        assert frame.order_intent is not None
        assert frame.order_intent.symbol == SYMBOL
        assert frame.execution_decision is not None

    def test_updates_metrics_on_success(self) -> None:
        emitter = ExecutionEmitter(_execution_service(), _portfolio_state)
        emitter.handle_frame(_frame())

        assert emitter.metrics.counter("order_intents_emitted_total").value == 1.0
        assert emitter.metrics.gauge("order_intent_latency_seconds").value >= 0.0

    def test_unapproved_decision_returns_none_without_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = ExecutionEmitter(_execution_service(), _portfolio_state)

        with caplog.at_level(logging.INFO, logger="app.execution_loop"):
            frame = emitter.handle_frame(_frame(approved=False))

        assert frame is None
        assert emitter.metrics.counter("order_intent_errors_total").value == 0.0
        not_built = [
            r for r in caplog.records if getattr(r, "event", None) == "order_intent_not_built"
        ]
        assert len(not_built) == 1

    def test_service_failure_is_logged_and_returns_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        emitter = ExecutionEmitter(
            _RaisingExecutionService(), _portfolio_state  # type: ignore[arg-type]
        )

        with caplog.at_level(logging.WARNING, logger="app.execution_loop"):
            frame = emitter.handle_frame(_frame())  # must not raise

        assert frame is None
        failures = [r for r in caplog.records if getattr(r, "event", None) == "order_intent_failed"]
        assert len(failures) == 1
        assert emitter.metrics.counter("order_intent_errors_total").value == 1.0
        assert _order_intent_events(caplog.records) == []

    def test_portfolio_state_provider_failure_is_logged_and_returns_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _boom() -> PortfolioState:
            raise RuntimeError("simulated provider failure")

        emitter = ExecutionEmitter(_execution_service(), _boom)

        with caplog.at_level(logging.WARNING, logger="app.execution_loop"):
            frame = emitter.handle_frame(_frame())  # must not raise

        assert frame is None
        failures = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "portfolio_state_provider_failed"
        ]
        assert len(failures) == 1
        assert emitter.metrics.counter("order_intent_errors_total").value == 1.0

    def test_raises_when_frame_missing_execution_decision(self) -> None:
        emitter = ExecutionEmitter(_execution_service(), _portfolio_state)
        with pytest.raises(ValueError, match="execution_decision"):
            emitter.handle_frame(RuntimeFrame(bar=_bar()))


class TestBrokerSubmissionEmitter:
    def test_accepted_submission_enriches_frame_and_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        adapter = MagicMock()
        adapter.submit_order.return_value = BrokerSubmissionResult(
            submitted=True, broker_order_id="order-1"
        )
        emitter = BrokerSubmissionEmitter(adapter, retry_policy=_NO_SLEEP_POLICY)

        with caplog.at_level(logging.INFO, logger="app.execution_loop"):
            frame = emitter.handle_frame(_order_intent_frame())

        assert frame is not None
        assert frame.broker_submission_result is not None
        assert frame.broker_submission_result.submitted is True
        assert frame.broker_submission_result.broker_order_id == "order-1"
        accepted = [
            r for r in caplog.records if getattr(r, "event", None) == "broker_submission_accepted"
        ]
        assert len(accepted) == 1
        assert emitter.metrics.counter("broker_submissions_accepted_total").value == 1.0

    def test_rejected_submission_still_enriches_frame_not_a_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        adapter = MagicMock()
        adapter.submit_order.return_value = BrokerSubmissionResult(
            submitted=False, error="persistent failure"
        )
        emitter = BrokerSubmissionEmitter(adapter, retry_policy=_NO_SLEEP_POLICY)

        with caplog.at_level(logging.WARNING, logger="app.execution_loop"):
            frame = emitter.handle_frame(_order_intent_frame())

        assert frame is not None
        assert frame.broker_submission_result is not None
        assert frame.broker_submission_result.submitted is False
        rejected = [
            r for r in caplog.records if getattr(r, "event", None) == "broker_submission_rejected"
        ]
        assert len(rejected) == 1
        assert emitter.metrics.counter("broker_submissions_rejected_total").value == 1.0

    def test_every_attempt_reuses_the_same_idempotency_key(self) -> None:
        adapter = MagicMock()
        adapter.submit_order.return_value = BrokerSubmissionResult(submitted=False, error="x")
        emitter = BrokerSubmissionEmitter(adapter, retry_policy=_NO_SLEEP_POLICY)
        frame = _order_intent_frame()

        emitter.handle_frame(frame)

        submitted_keys = {
            call.args[0].idempotency_key for call in adapter.submit_order.call_args_list
        }
        assert submitted_keys == {frame.require_order_intent().idempotency_key}

    def test_unexpected_exception_is_caught_and_returns_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        adapter = MagicMock()
        adapter.submit_order.side_effect = RuntimeError("adapter blew up")
        emitter = BrokerSubmissionEmitter(adapter, retry_policy=_NO_SLEEP_TRANSIENT_ONLY_POLICY)

        with caplog.at_level(logging.ERROR, logger="app.execution_loop"):
            frame = emitter.handle_frame(_order_intent_frame())  # must not raise

        assert frame is None
        raised = [
            r for r in caplog.records if getattr(r, "event", None) == "broker_submission_raised"
        ]
        assert len(raised) == 1
        assert emitter.metrics.counter("broker_submission_errors_total").value == 1.0

    def test_raises_when_frame_missing_order_intent(self) -> None:
        adapter = MagicMock()
        emitter = BrokerSubmissionEmitter(adapter, retry_policy=_NO_SLEEP_POLICY)
        with pytest.raises(ValueError, match="order_intent"):
            emitter.handle_frame(RuntimeFrame(bar=_bar()))
