"""Tests for `orchestration.evaluation` -- Phase C's cross-signal
comparison. No production influence is exercised or possible here: these
functions only read paired `(FinalDecision, LearningDecision | None,
NewsSignal | None)` history."""

from __future__ import annotations

import pytest

from orchestration.evaluation import evaluate, generate_evaluation_report
from orchestration.exceptions import OrchestrationError
from orchestration.policies.confidence import ConfidencePolicy
from orchestration.policies.consensus import ConsensusPolicy
from orchestration.policies.safety_first import SafetyFirstPolicy
from tests.orchestration.conftest import learning_decision, news_signal, strategy_decision


class TestEvaluateEmptyInput:
    def test_returns_zeroed_report(self) -> None:
        report = evaluate([])
        assert report["n"] == 0
        assert report["agreement_rate"] == 0.0


class TestEvaluatePairValidation:
    def test_rejects_learner_context_mismatch(self) -> None:
        decision = SafetyFirstPolicy().arbitrate(strategy_decision(), None, None)
        mismatched_learner = learning_decision(symbol="OTHER")
        with pytest.raises(OrchestrationError, match="does not match"):
            evaluate([(decision, mismatched_learner, None)])

    def test_rejects_news_symbol_not_covering_decision(self) -> None:
        decision = SafetyFirstPolicy().arbitrate(strategy_decision(), None, None)
        mismatched_news = news_signal(symbols=("OTHER",))
        with pytest.raises(OrchestrationError, match="does not cover"):
            evaluate([(decision, None, mismatched_news)])


class TestEvaluate:
    def test_agreement_rate_counts_confirmed_decisions(self) -> None:
        confirmed = SafetyFirstPolicy().arbitrate(strategy_decision(), None, None)
        adjusted = SafetyFirstPolicy().arbitrate(
            strategy_decision(allocation=0.7), learning_decision(recommended_allocation=0.1), None
        )
        report = evaluate(
            [
                (confirmed, None, None),
                (adjusted, learning_decision(recommended_allocation=0.1), None),
            ]
        )
        assert report["agreement_rate"] == pytest.approx(0.5)

    def test_override_frequency_complements_agreement_rate(self) -> None:
        confirmed = SafetyFirstPolicy().arbitrate(strategy_decision(), None, None)
        report = evaluate([(confirmed, None, None)])
        assert report["agreement_rate"] + report["override_frequency"] == pytest.approx(1.0)

    def test_signal_conflict_rate_requires_both_considered(self) -> None:
        decision = SafetyFirstPolicy().arbitrate(
            strategy_decision(allocation=0.7),
            learning_decision(recommended_allocation=0.7),  # agrees
            news_signal(
                sentiment_label="negative",
                sentiment_positive=0.1,
                sentiment_negative=0.8,
                sentiment_neutral=0.1,
            ),  # disagrees
        )
        report = evaluate(
            [
                (
                    decision,
                    learning_decision(recommended_allocation=0.7),
                    news_signal(
                        sentiment_label="negative",
                        sentiment_positive=0.1,
                        sentiment_negative=0.8,
                        sentiment_neutral=0.1,
                    ),
                )
            ]
        )
        assert report["signal_conflict_rate"] == 1.0

    def test_signal_conflict_rate_zero_when_only_one_considered(self) -> None:
        decision = SafetyFirstPolicy().arbitrate(
            strategy_decision(allocation=0.7), learning_decision(recommended_allocation=0.7), None
        )
        report = evaluate([(decision, learning_decision(recommended_allocation=0.7), None)])
        assert report["signal_conflict_rate"] == 0.0

    def test_strategy_vs_learner_divergence(self) -> None:
        learning = learning_decision(recommended_allocation=0.3)
        decision = SafetyFirstPolicy().arbitrate(strategy_decision(allocation=0.7), learning, None)
        report = evaluate([(decision, learning, None)])
        assert report["strategy_vs_learner_divergence"] == pytest.approx(0.4)

    def test_strategy_vs_learner_divergence_zero_without_learner(self) -> None:
        decision = SafetyFirstPolicy().arbitrate(strategy_decision(), None, None)
        report = evaluate([(decision, None, None)])
        assert report["strategy_vs_learner_divergence"] == 0.0

    def test_news_alignment_measures_agreement_among_paired_news(self) -> None:
        agreeing_news = news_signal(sentiment_label="positive")
        agreeing_decision = SafetyFirstPolicy().arbitrate(
            strategy_decision(allocation=0.7), None, agreeing_news
        )
        disagreeing_news = news_signal(
            sentiment_label="negative",
            sentiment_positive=0.1,
            sentiment_negative=0.8,
            sentiment_neutral=0.1,
        )
        disagreeing_decision = SafetyFirstPolicy().arbitrate(
            strategy_decision(allocation=0.7), None, disagreeing_news
        )
        report = evaluate(
            [
                (agreeing_decision, None, agreeing_news),
                (disagreeing_decision, None, disagreeing_news),
            ]
        )
        assert report["news_alignment"] == pytest.approx(0.5)

    def test_orchestration_confidence_averages_decision_confidence(self) -> None:
        low = ConsensusPolicy().arbitrate(
            strategy_decision(allocation=0.7, confidence=0.0),
            learning_decision(recommended_allocation=0.1),
            None,
        )
        high = SafetyFirstPolicy().arbitrate(strategy_decision(confidence=1.0), None, None)
        report = evaluate(
            [(low, learning_decision(recommended_allocation=0.1), None), (high, None, None)]
        )
        assert report["orchestration_confidence"] == pytest.approx(0.5)

    def test_confidence_policy_decisions_evaluate_normally(self) -> None:
        decision = ConfidencePolicy().arbitrate(
            strategy_decision(allocation=0.7, confidence=0.8),
            learning_decision(confidence=0.4),
            None,
        )
        report = evaluate([(decision, learning_decision(confidence=0.4), None)])
        assert report["n"] == 1


class TestGenerateEvaluationReport:
    def test_report_is_nonempty_string(self) -> None:
        decision = SafetyFirstPolicy().arbitrate(strategy_decision(), None, None)
        report = generate_evaluation_report([(decision, None, None)])
        assert isinstance(report, str)
        assert "Signal Orchestration Evaluation Report" in report

    def test_report_includes_key_metrics(self) -> None:
        decision = SafetyFirstPolicy().arbitrate(strategy_decision(), None, None)
        report = generate_evaluation_report([(decision, None, None)])
        assert "Agreement rate" in report
        assert "Override frequency" in report
        assert "Signal conflict rate" in report
        assert "News alignment" in report

    def test_report_handles_empty_input(self) -> None:
        report = generate_evaluation_report([])
        assert "Decisions: 0" in report
