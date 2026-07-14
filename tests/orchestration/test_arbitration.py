"""Tests for `orchestration.arbitration.arbitrate` -- Phase A's single
deterministic arbitration rule. `StrategyDecision` is primary;
`LearningDecision`/`NewsSignal` are advisory only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memory.models import LearningDecision
from nlp.models import NewsSignal
from orchestration.arbitration import arbitrate
from orchestration.config import OrchestrationConfig
from orchestration.exceptions import MismatchedSignalError
from orchestration.models import ArbitrationOutcome
from strategy.models import StrategyDecision

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _strategy_decision(**overrides: object) -> StrategyDecision:
    defaults: dict[str, object] = {
        "timestamp": T0,
        "symbol": "TEST",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "allocation": 0.7,
        "confidence": 0.8,
        "expected_holding_period": timedelta(days=5),
        "reasoning": "regime favors growth",
        "metadata": {},
    }
    defaults.update(overrides)
    return StrategyDecision(**defaults)  # type: ignore[arg-type]


def _learning_decision(**overrides: object) -> LearningDecision:
    defaults: dict[str, object] = {
        "timestamp": T0,
        "symbol": "TEST",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "production_allocation": 0.7,
        "recommended_allocation": 0.7,
        "confidence": 0.6,
        "sample_size": 20,
        "rationale": "posterior mean 0.9 across 20 samples",
        "model_version": "thompson-bandit-v1",
        "metadata": {},
    }
    defaults.update(overrides)
    return LearningDecision(**defaults)  # type: ignore[arg-type]


def _news_signal(**overrides: object) -> NewsSignal:
    defaults: dict[str, object] = {
        "signal_id": "alpaca_news:1",
        "source_id": "1",
        "source": "alpaca_news",
        "symbols": ("TEST",),
        "entities": (),
        "headline": "Company reports strong earnings",
        "published_at": T0,
        "processed_at": T0 + timedelta(seconds=5),
        "sentiment_positive": 0.8,
        "sentiment_negative": 0.1,
        "sentiment_neutral": 0.1,
        "sentiment_label": "positive",
        "model_version": "finbert-v1",
        "metadata": {},
    }
    defaults.update(overrides)
    return NewsSignal(**defaults)  # type: ignore[arg-type]


class TestNoAdvisorySignals:
    def test_no_signals_confirms_primary(self) -> None:
        strategy_decision = _strategy_decision()
        decision = arbitrate(strategy_decision, None, None)
        assert decision.outcome is ArbitrationOutcome.CONFIRMED
        assert decision.final_allocation == decision.primary_allocation == 0.7
        assert decision.learner_input.considered is False
        assert decision.news_input.considered is False

    def test_carries_over_primary_context(self) -> None:
        strategy_decision = _strategy_decision(symbol="AAPL", strategy_id="bear_v1", regime_id=2)
        decision = arbitrate(strategy_decision, None, None)
        assert decision.symbol == "AAPL"
        assert decision.strategy_id == "bear_v1"
        assert decision.regime_id == 2
        assert decision.timestamp == strategy_decision.timestamp

    def test_confidence_unchanged_when_confirmed(self) -> None:
        strategy_decision = _strategy_decision(confidence=0.9)
        decision = arbitrate(strategy_decision, None, None)
        assert decision.confidence == pytest.approx(0.9)


class TestLearnerOnly:
    def test_learner_agreement_confirms(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.7)
        learning_decision = _learning_decision(recommended_allocation=0.72)
        decision = arbitrate(strategy_decision, learning_decision, None)
        assert decision.outcome is ArbitrationOutcome.CONFIRMED
        assert decision.learner_input.considered is True
        assert decision.learner_input.agrees is True
        assert decision.learner_input.weight == 0.0

    def test_learner_disagreement_adjusts(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.7)
        learning_decision = _learning_decision(recommended_allocation=0.2)
        decision = arbitrate(
            strategy_decision,
            learning_decision,
            None,
            config=OrchestrationConfig(disagreement_penalty=0.5),
        )
        assert decision.outcome is ArbitrationOutcome.ADJUSTED
        assert decision.final_allocation == pytest.approx(0.35)
        assert decision.learner_input.agrees is False
        assert decision.learner_input.weight == pytest.approx(0.5)

    def test_learner_agreement_within_tolerance_boundary(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.7)
        learning_decision = _learning_decision(recommended_allocation=0.65)
        decision = arbitrate(
            strategy_decision,
            learning_decision,
            None,
            config=OrchestrationConfig(agreement_tolerance=0.05),
        )
        assert decision.learner_input.agrees is True


class TestNewsOnly:
    def test_positive_sentiment_agrees(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.7)
        news_signal = _news_signal(sentiment_label="positive")
        decision = arbitrate(strategy_decision, None, news_signal)
        assert decision.news_input.agrees is True
        assert decision.outcome is ArbitrationOutcome.CONFIRMED

    def test_neutral_sentiment_agrees(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.7)
        news_signal = _news_signal(
            sentiment_label="neutral",
            sentiment_positive=0.2,
            sentiment_negative=0.2,
            sentiment_neutral=0.6,
        )
        decision = arbitrate(strategy_decision, None, news_signal)
        assert decision.news_input.agrees is True

    def test_negative_sentiment_disagrees_and_adjusts(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.7)
        news_signal = _news_signal(
            sentiment_label="negative",
            sentiment_positive=0.1,
            sentiment_negative=0.8,
            sentiment_neutral=0.1,
        )
        decision = arbitrate(
            strategy_decision,
            None,
            news_signal,
            config=OrchestrationConfig(disagreement_penalty=0.5),
        )
        assert decision.news_input.agrees is False
        assert decision.outcome is ArbitrationOutcome.ADJUSTED
        assert decision.final_allocation == pytest.approx(0.35)


class TestBothAdvisorySignals:
    def test_both_agree_confirms(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.7)
        learning_decision = _learning_decision(recommended_allocation=0.7)
        news_signal = _news_signal(sentiment_label="positive")
        decision = arbitrate(strategy_decision, learning_decision, news_signal)
        assert decision.outcome is ArbitrationOutcome.CONFIRMED

    def test_one_disagrees_adjusts(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.7)
        learning_decision = _learning_decision(recommended_allocation=0.7)
        news_signal = _news_signal(
            sentiment_label="negative",
            sentiment_positive=0.1,
            sentiment_negative=0.8,
            sentiment_neutral=0.1,
        )
        decision = arbitrate(
            strategy_decision,
            learning_decision,
            news_signal,
            config=OrchestrationConfig(disagreement_penalty=0.4),
        )
        assert decision.outcome is ArbitrationOutcome.ADJUSTED
        assert decision.final_allocation == pytest.approx(0.7 * 0.6)
        assert decision.learner_input.weight == 0.0
        assert decision.news_input.weight == pytest.approx(0.4)

    def test_both_disagree_suppresses(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.7)
        learning_decision = _learning_decision(recommended_allocation=0.1)
        news_signal = _news_signal(
            sentiment_label="negative",
            sentiment_positive=0.1,
            sentiment_negative=0.8,
            sentiment_neutral=0.1,
        )
        decision = arbitrate(strategy_decision, learning_decision, news_signal)
        assert decision.outcome is ArbitrationOutcome.SUPPRESSED
        assert decision.final_allocation == 0.0
        assert decision.learner_input.weight == pytest.approx(0.5)
        assert decision.news_input.weight == pytest.approx(0.5)

    def test_zero_primary_allocation_always_confirms_at_zero(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.0)
        learning_decision = _learning_decision(
            production_allocation=0.0, recommended_allocation=0.9
        )
        news_signal = _news_signal(
            sentiment_label="negative",
            sentiment_positive=0.1,
            sentiment_negative=0.8,
            sentiment_neutral=0.1,
        )
        decision = arbitrate(strategy_decision, learning_decision, news_signal)
        assert decision.outcome is ArbitrationOutcome.CONFIRMED
        assert decision.final_allocation == 0.0
        assert decision.learner_input.agrees is True
        assert decision.news_input.agrees is True


class TestContextValidation:
    def test_rejects_learner_symbol_mismatch(self) -> None:
        strategy_decision = _strategy_decision(symbol="AAPL")
        learning_decision = _learning_decision(symbol="MSFT")
        with pytest.raises(MismatchedSignalError, match="symbol"):
            arbitrate(strategy_decision, learning_decision, None)

    def test_rejects_learner_strategy_id_mismatch(self) -> None:
        strategy_decision = _strategy_decision(strategy_id="growth_v1")
        learning_decision = _learning_decision(strategy_id="bear_v1")
        with pytest.raises(MismatchedSignalError, match="strategy_id"):
            arbitrate(strategy_decision, learning_decision, None)

    def test_rejects_learner_regime_id_mismatch(self) -> None:
        strategy_decision = _strategy_decision(regime_id=0)
        learning_decision = _learning_decision(regime_id=1)
        with pytest.raises(MismatchedSignalError, match="regime_id"):
            arbitrate(strategy_decision, learning_decision, None)

    def test_rejects_news_symbol_not_in_signal_symbols(self) -> None:
        strategy_decision = _strategy_decision(symbol="AAPL")
        news_signal = _news_signal(symbols=("MSFT",))
        with pytest.raises(MismatchedSignalError, match="symbols"):
            arbitrate(strategy_decision, None, news_signal)

    def test_allows_news_symbol_among_several(self) -> None:
        strategy_decision = _strategy_decision(symbol="AAPL")
        news_signal = _news_signal(symbols=("MSFT", "AAPL", "GOOG"))
        decision = arbitrate(strategy_decision, None, news_signal)
        assert decision.news_input.considered is True


class TestDeterminism:
    def test_same_inputs_produce_equal_decision(self) -> None:
        strategy_decision = _strategy_decision()
        learning_decision = _learning_decision(recommended_allocation=0.3)
        news_signal = _news_signal(sentiment_label="positive")
        first = arbitrate(strategy_decision, learning_decision, news_signal)
        second = arbitrate(strategy_decision, learning_decision, news_signal)
        assert first == second


class TestRationale:
    def test_rationale_mentions_no_signals(self) -> None:
        decision = arbitrate(_strategy_decision(), None, None)
        assert "no learner signal considered" in decision.rationale
        assert "no news signal considered" in decision.rationale

    def test_rationale_mentions_considered_signals(self) -> None:
        strategy_decision = _strategy_decision()
        learning_decision = _learning_decision(recommended_allocation=0.7)
        news_signal = _news_signal(sentiment_label="positive")
        decision = arbitrate(strategy_decision, learning_decision, news_signal)
        assert "learner recommended" in decision.rationale
        assert "news sentiment" in decision.rationale
