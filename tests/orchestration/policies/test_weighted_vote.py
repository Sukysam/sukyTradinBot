"""Tests for `orchestration.policies.WeightedVotePolicy` -- a continuous,
weighted-average blend rather than a discrete disagreement threshold.
Structurally can never fully suppress a decision as long as
`strategy_weight > 0`."""

from __future__ import annotations

import pytest

from orchestration.models import ArbitrationOutcome
from orchestration.policies.weighted_vote import WeightedVotePolicy
from tests.orchestration.conftest import learning_decision, news_signal, strategy_decision


class TestWeightedVotePolicy:
    def test_rejects_nonpositive_strategy_weight(self) -> None:
        with pytest.raises(ValueError, match="strategy_weight"):
            WeightedVotePolicy(strategy_weight=0.0)

    def test_rejects_negative_learner_weight(self) -> None:
        with pytest.raises(ValueError, match="learner_weight"):
            WeightedVotePolicy(learner_weight=-0.1)

    def test_rejects_negative_news_weight(self) -> None:
        with pytest.raises(ValueError, match="news_weight"):
            WeightedVotePolicy(news_weight=-0.1)

    def test_no_signals_confirms_at_full_multiplier(self) -> None:
        decision = WeightedVotePolicy().arbitrate(strategy_decision(), None, None)
        assert decision.outcome is ArbitrationOutcome.CONFIRMED
        assert decision.final_allocation == decision.primary_allocation

    def test_both_agree_confirms(self) -> None:
        decision = WeightedVotePolicy().arbitrate(
            strategy_decision(allocation=0.7),
            learning_decision(recommended_allocation=0.7),
            news_signal(sentiment_label="positive"),
        )
        assert decision.outcome is ArbitrationOutcome.CONFIRMED

    def test_single_disagreement_reduces_but_never_to_zero(self) -> None:
        decision = WeightedVotePolicy(
            strategy_weight=1.0, learner_weight=0.5, news_weight=0.5
        ).arbitrate(
            strategy_decision(allocation=0.7),
            learning_decision(recommended_allocation=0.1),
            None,
        )
        # multiplier = (1.0*1.0 + 0.5*0.0) / 1.5 = 2/3
        assert decision.final_allocation == pytest.approx(0.7 * (2 / 3))
        assert decision.outcome is ArbitrationOutcome.ADJUSTED
        assert decision.final_allocation > 0.0

    def test_double_disagreement_never_fully_suppresses(self) -> None:
        decision = WeightedVotePolicy().arbitrate(
            strategy_decision(allocation=0.7),
            learning_decision(recommended_allocation=0.1),
            news_signal(
                sentiment_label="negative",
                sentiment_positive=0.1,
                sentiment_negative=0.8,
                sentiment_neutral=0.1,
            ),
        )
        assert decision.final_allocation > 0.0
        assert decision.outcome is ArbitrationOutcome.ADJUSTED

    def test_zero_primary_allocation_confirms_at_zero(self) -> None:
        decision = WeightedVotePolicy().arbitrate(
            strategy_decision(allocation=0.0),
            learning_decision(production_allocation=0.0, recommended_allocation=0.9),
            None,
        )
        assert decision.final_allocation == 0.0
        assert decision.outcome is ArbitrationOutcome.CONFIRMED

    def test_never_exceeds_primary_allocation(self) -> None:
        decision = WeightedVotePolicy(learner_weight=5.0, news_weight=5.0).arbitrate(
            strategy_decision(allocation=0.7),
            learning_decision(recommended_allocation=0.7),
            news_signal(sentiment_label="positive"),
        )
        assert decision.final_allocation <= decision.primary_allocation

    def test_weights_normalize_to_vote_share(self) -> None:
        decision = WeightedVotePolicy(
            strategy_weight=1.0, learner_weight=1.0, news_weight=0.0
        ).arbitrate(
            strategy_decision(allocation=0.7),
            learning_decision(recommended_allocation=0.1),
            None,
        )
        assert decision.learner_input.weight == pytest.approx(0.5)
