"""Tests for `orchestration.policies.SafetyFirstPolicy` -- Phase A's
original rule, now behind `ArbitrationPolicy`. Full agreement/
disagreement behavior is exercised via `tests/orchestration/
test_arbitration.py` (which calls it through `arbitrate`'s default);
these tests confirm the class itself is directly usable and produces
identical output to that default path."""

from __future__ import annotations

from orchestration.arbitration import arbitrate
from orchestration.config import OrchestrationConfig
from orchestration.models import ArbitrationOutcome
from orchestration.policies.safety_first import SafetyFirstPolicy
from tests.orchestration.conftest import learning_decision, news_signal, strategy_decision


class TestSafetyFirstPolicy:
    def test_matches_arbitrate_default(self) -> None:
        decision_strategy = strategy_decision()
        learning = learning_decision(recommended_allocation=0.3)
        news = news_signal(sentiment_label="positive")

        via_arbitrate = arbitrate(decision_strategy, learning, news)
        via_policy = SafetyFirstPolicy().arbitrate(decision_strategy, learning, news)

        assert via_arbitrate == via_policy

    def test_respects_custom_config(self) -> None:
        decision_strategy = strategy_decision(allocation=0.7)
        learning = learning_decision(recommended_allocation=0.1)
        policy = SafetyFirstPolicy(config=OrchestrationConfig(disagreement_penalty=0.3))
        decision = policy.arbitrate(decision_strategy, learning, None)
        assert decision.outcome is ArbitrationOutcome.ADJUSTED
        assert decision.final_allocation == 0.7 * 0.7
