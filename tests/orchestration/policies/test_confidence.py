"""Tests for `orchestration.policies.ConfidencePolicy` -- scales
`final_allocation` by advisory confidence relative to the strategy's own
confidence, independent of directional agreement."""

from __future__ import annotations

import pytest

from orchestration.models import ArbitrationOutcome
from orchestration.policies.confidence import ConfidencePolicy
from tests.orchestration.conftest import learning_decision, news_signal, strategy_decision


class TestConfidencePolicy:
    def test_no_signals_confirms_at_full_multiplier(self) -> None:
        decision = ConfidencePolicy().arbitrate(strategy_decision(), None, None)
        assert decision.outcome is ArbitrationOutcome.CONFIRMED
        assert decision.final_allocation == decision.primary_allocation

    def test_learner_confidence_equal_to_strategy_confirms(self) -> None:
        decision = ConfidencePolicy().arbitrate(
            strategy_decision(allocation=0.7, confidence=0.8),
            learning_decision(confidence=0.8),
            None,
        )
        assert decision.outcome is ArbitrationOutcome.CONFIRMED
        assert decision.final_allocation == pytest.approx(0.7)

    def test_learner_confidence_below_strategy_adjusts_proportionally(self) -> None:
        decision = ConfidencePolicy().arbitrate(
            strategy_decision(allocation=0.7, confidence=0.8),
            learning_decision(confidence=0.4),
            None,
        )
        assert decision.outcome is ArbitrationOutcome.ADJUSTED
        assert decision.final_allocation == pytest.approx(0.7 * 0.5)

    def test_learner_confidence_above_strategy_is_capped_at_full_allocation(self) -> None:
        decision = ConfidencePolicy().arbitrate(
            strategy_decision(allocation=0.7, confidence=0.5),
            learning_decision(confidence=0.9),
            None,
        )
        assert decision.outcome is ArbitrationOutcome.CONFIRMED
        assert decision.final_allocation == pytest.approx(0.7)

    def test_news_model_confidence_is_max_of_three_scores(self) -> None:
        decision = ConfidencePolicy().arbitrate(
            strategy_decision(allocation=0.7, confidence=0.8),
            None,
            news_signal(
                sentiment_label="neutral",
                sentiment_positive=0.3,
                sentiment_negative=0.3,
                sentiment_neutral=0.4,
            ),
        )
        # news model confidence = 0.4; multiplier = 0.4/0.8 = 0.5
        assert decision.final_allocation == pytest.approx(0.7 * 0.5)

    def test_zero_strategy_confidence_with_advisory_signal_suppresses(self) -> None:
        decision = ConfidencePolicy().arbitrate(
            strategy_decision(allocation=0.7, confidence=0.0),
            learning_decision(confidence=0.5),
            None,
        )
        assert decision.outcome is ArbitrationOutcome.SUPPRESSED
        assert decision.final_allocation == 0.0

    def test_zero_primary_allocation_confirms_at_zero(self) -> None:
        decision = ConfidencePolicy().arbitrate(
            strategy_decision(allocation=0.0),
            learning_decision(production_allocation=0.0, confidence=0.9),
            None,
        )
        assert decision.final_allocation == 0.0
        assert decision.outcome is ArbitrationOutcome.CONFIRMED

    def test_agrees_field_still_reflects_direction_not_confidence(self) -> None:
        # Learner disagrees in direction (very different recommended
        # allocation) but has high confidence -- agrees should still
        # reflect the direction check, independent of the confidence math.
        decision = ConfidencePolicy().arbitrate(
            strategy_decision(allocation=0.7, confidence=0.5),
            learning_decision(recommended_allocation=0.1, confidence=0.9),
            None,
        )
        assert decision.learner_input.agrees is False
        assert (
            decision.outcome is ArbitrationOutcome.CONFIRMED
        )  # driven by confidence, not agreement
