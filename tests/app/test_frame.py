"""Tests for `app.frame.RuntimeFrame`'s enrichment-order invariant and
`with_*` helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.frame import RuntimeFrame
from execution.broker_adapter import BrokerSubmissionResult
from execution.models import OrderIntent, OrderSide, OrderType, TimeInForce
from features.feature_vector import FeatureVector, Provenance
from hmm.models import RegimeState
from market_data.models import Bar, Timeframe
from orchestration.models import ArbitrationOutcome, FinalDecision, SignalInput
from risk.models import DecisionType, ExecutionDecision
from strategy.models import StrategyDecision

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bar() -> Bar:
    return Bar(
        symbol="AAPL",
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
        symbol="AAPL",
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
        symbol="AAPL",
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
        symbol="AAPL",
        strategy_id="growth",
        regime_id=0,
        allocation=0.5,
        confidence=0.8,
        expected_holding_period=timedelta(days=20),
        reasoning="test",
        metadata={},
    )


def _final_decision() -> FinalDecision:
    absent = SignalInput(source="memory", considered=False, agrees=False, weight=0.0)
    return FinalDecision(
        timestamp=T0,
        symbol="AAPL",
        strategy_id="growth",
        regime_id=0,
        primary_allocation=0.5,
        final_allocation=0.5,
        confidence=0.8,
        outcome=ArbitrationOutcome.CONFIRMED,
        learner_input=absent,
        news_input=SignalInput(source="nlp", considered=False, agrees=False, weight=0.0),
        rationale="test",
        metadata={},
    )


def _execution_decision() -> ExecutionDecision:
    return ExecutionDecision(
        timestamp=T0,
        symbol="AAPL",
        approved=True,
        approved_allocation=0.5,
        decision_type=DecisionType.APPROVED,
        risk_adjustments=(),
        reasoning="test",
        strategy_reference=_strategy_decision(),
        metadata={},
    )


def _order_intent() -> OrderIntent:
    decision = _execution_decision()
    return OrderIntent(
        timestamp=T0,
        symbol="AAPL",
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


def _broker_submission_result() -> BrokerSubmissionResult:
    return BrokerSubmissionResult(submitted=True, broker_order_id="order-1")


class TestRuntimeFrame:
    def test_bar_only_frame_constructs(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        assert frame.feature_vector is None
        assert frame.regime_state is None
        assert frame.strategy_decision is None

    def test_rejects_regime_state_without_feature_vector(self) -> None:
        with pytest.raises(ValueError, match="feature_vector"):
            RuntimeFrame(bar=_bar(), regime_state=_regime_state())

    def test_rejects_strategy_decision_without_regime_state(self) -> None:
        with pytest.raises(ValueError, match="regime_state"):
            RuntimeFrame(
                bar=_bar(), feature_vector=_feature_vector(), strategy_decision=_strategy_decision()
            )

    def test_rejects_final_decision_without_strategy_decision(self) -> None:
        with pytest.raises(ValueError, match="strategy_decision"):
            RuntimeFrame(
                bar=_bar(),
                feature_vector=_feature_vector(),
                regime_state=_regime_state(),
                final_decision=_final_decision(),
            )

    def test_with_feature_vector_enriches_without_mutating_original(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        vector = _feature_vector()
        enriched = frame.with_feature_vector(vector)

        assert frame.feature_vector is None
        assert enriched.feature_vector is vector
        assert enriched.bar == frame.bar

    def test_with_regime_state_enriches_without_mutating_original(self) -> None:
        frame = RuntimeFrame(bar=_bar(), feature_vector=_feature_vector())
        state = _regime_state()
        enriched = frame.with_regime_state(state)

        assert frame.regime_state is None
        assert enriched.regime_state is state
        assert enriched.feature_vector == frame.feature_vector

    def test_with_strategy_decision_enriches_without_mutating_original(self) -> None:
        frame = RuntimeFrame(
            bar=_bar(), feature_vector=_feature_vector(), regime_state=_regime_state()
        )
        decision = _strategy_decision()
        enriched = frame.with_strategy_decision(decision)

        assert frame.strategy_decision is None
        assert enriched.strategy_decision is decision
        assert enriched.regime_state == frame.regime_state

    def test_with_final_decision_enriches_without_mutating_original(self) -> None:
        frame = RuntimeFrame(
            bar=_bar(),
            feature_vector=_feature_vector(),
            regime_state=_regime_state(),
            strategy_decision=_strategy_decision(),
        )
        decision = _final_decision()
        enriched = frame.with_final_decision(decision)

        assert frame.final_decision is None
        assert enriched.final_decision is decision
        assert enriched.strategy_decision == frame.strategy_decision

    def test_rejects_execution_decision_without_final_decision(self) -> None:
        with pytest.raises(ValueError, match="final_decision"):
            RuntimeFrame(
                bar=_bar(),
                feature_vector=_feature_vector(),
                regime_state=_regime_state(),
                strategy_decision=_strategy_decision(),
                execution_decision=_execution_decision(),
            )

    def test_with_execution_decision_enriches_without_mutating_original(self) -> None:
        frame = RuntimeFrame(
            bar=_bar(),
            feature_vector=_feature_vector(),
            regime_state=_regime_state(),
            strategy_decision=_strategy_decision(),
            final_decision=_final_decision(),
        )
        decision = _execution_decision()
        enriched = frame.with_execution_decision(decision)

        assert frame.execution_decision is None
        assert enriched.execution_decision is decision
        assert enriched.final_decision == frame.final_decision

    def test_require_feature_vector_returns_the_value_when_present(self) -> None:
        vector = _feature_vector()
        frame = RuntimeFrame(bar=_bar(), feature_vector=vector)
        assert frame.require_feature_vector() is vector

    def test_require_feature_vector_raises_when_absent(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        with pytest.raises(ValueError, match="feature_vector"):
            frame.require_feature_vector()

    def test_require_regime_state_returns_the_value_when_present(self) -> None:
        state = _regime_state()
        frame = RuntimeFrame(bar=_bar(), feature_vector=_feature_vector(), regime_state=state)
        assert frame.require_regime_state() is state

    def test_require_regime_state_raises_when_absent(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        with pytest.raises(ValueError, match="regime_state"):
            frame.require_regime_state()

    def test_require_strategy_decision_returns_the_value_when_present(self) -> None:
        decision = _strategy_decision()
        frame = RuntimeFrame(
            bar=_bar(),
            feature_vector=_feature_vector(),
            regime_state=_regime_state(),
            strategy_decision=decision,
        )
        assert frame.require_strategy_decision() is decision

    def test_require_strategy_decision_raises_when_absent(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        with pytest.raises(ValueError, match="strategy_decision"):
            frame.require_strategy_decision()

    def test_require_final_decision_returns_the_value_when_present(self) -> None:
        decision = _final_decision()
        frame = RuntimeFrame(
            bar=_bar(),
            feature_vector=_feature_vector(),
            regime_state=_regime_state(),
            strategy_decision=_strategy_decision(),
            final_decision=decision,
        )
        assert frame.require_final_decision() is decision

    def test_require_final_decision_raises_when_absent(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        with pytest.raises(ValueError, match="final_decision"):
            frame.require_final_decision()

    def test_require_execution_decision_returns_the_value_when_present(self) -> None:
        decision = _execution_decision()
        frame = RuntimeFrame(
            bar=_bar(),
            feature_vector=_feature_vector(),
            regime_state=_regime_state(),
            strategy_decision=_strategy_decision(),
            final_decision=_final_decision(),
            execution_decision=decision,
        )
        assert frame.require_execution_decision() is decision

    def test_require_execution_decision_raises_when_absent(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        with pytest.raises(ValueError, match="execution_decision"):
            frame.require_execution_decision()

    def test_rejects_order_intent_without_execution_decision(self) -> None:
        with pytest.raises(ValueError, match="execution_decision"):
            RuntimeFrame(
                bar=_bar(),
                feature_vector=_feature_vector(),
                regime_state=_regime_state(),
                strategy_decision=_strategy_decision(),
                final_decision=_final_decision(),
                order_intent=_order_intent(),
            )

    def test_with_order_intent_enriches_without_mutating_original(self) -> None:
        frame = RuntimeFrame(
            bar=_bar(),
            feature_vector=_feature_vector(),
            regime_state=_regime_state(),
            strategy_decision=_strategy_decision(),
            final_decision=_final_decision(),
            execution_decision=_execution_decision(),
        )
        intent = _order_intent()
        enriched = frame.with_order_intent(intent)

        assert frame.order_intent is None
        assert enriched.order_intent is intent
        assert enriched.execution_decision == frame.execution_decision

    def test_require_order_intent_returns_the_value_when_present(self) -> None:
        intent = _order_intent()
        frame = RuntimeFrame(
            bar=_bar(),
            feature_vector=_feature_vector(),
            regime_state=_regime_state(),
            strategy_decision=_strategy_decision(),
            final_decision=_final_decision(),
            execution_decision=_execution_decision(),
            order_intent=intent,
        )
        assert frame.require_order_intent() is intent

    def test_require_order_intent_raises_when_absent(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        with pytest.raises(ValueError, match="order_intent"):
            frame.require_order_intent()

    def test_rejects_broker_submission_result_without_order_intent(self) -> None:
        with pytest.raises(ValueError, match="order_intent"):
            RuntimeFrame(
                bar=_bar(),
                feature_vector=_feature_vector(),
                regime_state=_regime_state(),
                strategy_decision=_strategy_decision(),
                final_decision=_final_decision(),
                execution_decision=_execution_decision(),
                broker_submission_result=_broker_submission_result(),
            )

    def test_with_broker_submission_result_enriches_without_mutating_original(self) -> None:
        frame = RuntimeFrame(
            bar=_bar(),
            feature_vector=_feature_vector(),
            regime_state=_regime_state(),
            strategy_decision=_strategy_decision(),
            final_decision=_final_decision(),
            execution_decision=_execution_decision(),
            order_intent=_order_intent(),
        )
        result = _broker_submission_result()
        enriched = frame.with_broker_submission_result(result)

        assert frame.broker_submission_result is None
        assert enriched.broker_submission_result is result
        assert enriched.order_intent == frame.order_intent

    def test_require_broker_submission_result_returns_the_value_when_present(self) -> None:
        result = _broker_submission_result()
        frame = RuntimeFrame(
            bar=_bar(),
            feature_vector=_feature_vector(),
            regime_state=_regime_state(),
            strategy_decision=_strategy_decision(),
            final_decision=_final_decision(),
            execution_decision=_execution_decision(),
            order_intent=_order_intent(),
            broker_submission_result=result,
        )
        assert frame.require_broker_submission_result() is result

    def test_require_broker_submission_result_raises_when_absent(self) -> None:
        frame = RuntimeFrame(bar=_bar())
        with pytest.raises(ValueError, match="broker_submission_result"):
            frame.require_broker_submission_result()
