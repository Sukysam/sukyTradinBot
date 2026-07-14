"""Tests for `orchestration.policies.ConsensusPolicy` -- any considered
advisory signal disagreeing suppresses the decision entirely, stricter
than `SafetyFirstPolicy`'s two-disagreement threshold."""

from __future__ import annotations

import pytest

from orchestration.models import ArbitrationOutcome
from orchestration.policies.consensus import ConsensusPolicy
from tests.orchestration.conftest import learning_decision, news_signal, strategy_decision


class TestConsensusPolicy:
    def test_no_signals_confirms(self) -> None:
        decision = ConsensusPolicy().arbitrate(strategy_decision(), None, None)
        assert decision.outcome is ArbitrationOutcome.CONFIRMED
        assert decision.final_allocation == decision.primary_allocation

    def test_both_agree_confirms(self) -> None:
        decision = ConsensusPolicy().arbitrate(
            strategy_decision(allocation=0.7),
            learning_decision(recommended_allocation=0.7),
            news_signal(sentiment_label="positive"),
        )
        assert decision.outcome is ArbitrationOutcome.CONFIRMED

    def test_single_disagreement_suppresses(self) -> None:
        decision = ConsensusPolicy().arbitrate(
            strategy_decision(allocation=0.7),
            learning_decision(recommended_allocation=0.1),
            None,
        )
        assert decision.outcome is ArbitrationOutcome.SUPPRESSED
        assert decision.final_allocation == 0.0

    def test_single_disagreement_dissenter_carries_full_weight(self) -> None:
        decision = ConsensusPolicy().arbitrate(
            strategy_decision(allocation=0.7),
            learning_decision(recommended_allocation=0.1),
            news_signal(sentiment_label="positive"),
        )
        assert decision.learner_input.weight == pytest.approx(1.0)
        assert decision.news_input.weight == pytest.approx(0.0)

    def test_both_disagree_suppresses(self) -> None:
        decision = ConsensusPolicy().arbitrate(
            strategy_decision(allocation=0.7),
            learning_decision(recommended_allocation=0.1),
            news_signal(
                sentiment_label="negative",
                sentiment_positive=0.1,
                sentiment_negative=0.8,
                sentiment_neutral=0.1,
            ),
        )
        assert decision.outcome is ArbitrationOutcome.SUPPRESSED

    def test_suppressed_decision_has_zero_confidence(self) -> None:
        decision = ConsensusPolicy().arbitrate(
            strategy_decision(allocation=0.7, confidence=0.9),
            learning_decision(recommended_allocation=0.1),
            None,
        )
        assert decision.confidence == 0.0

    def test_confirmed_decision_keeps_strategy_confidence(self) -> None:
        decision = ConsensusPolicy().arbitrate(
            strategy_decision(allocation=0.7, confidence=0.9), None, None
        )
        assert decision.confidence == pytest.approx(0.9)

    def test_zero_primary_allocation_always_confirms(self) -> None:
        decision = ConsensusPolicy().arbitrate(
            strategy_decision(allocation=0.0),
            learning_decision(production_allocation=0.0, recommended_allocation=0.9),
            None,
        )
        assert decision.outcome is ArbitrationOutcome.CONFIRMED
        assert decision.final_allocation == 0.0
