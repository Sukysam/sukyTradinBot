"""Milestone 11's performance targets, measured -- not assumed.

| Metric                                    | Target  |
|----------------------------------------------|---------|
| SafetyFirstPolicy.arbitrate                   | < 0.1ms |
| ConsensusPolicy.arbitrate                     | < 0.1ms |
| WeightedVotePolicy.arbitrate                  | < 0.1ms |
| ConfidencePolicy.arbitrate                    | < 0.1ms |

All four are pure in-memory, no I/O -- comparable in spirit to
`tests/risk/test_performance.py`'s `RiskService.decide` measurement.
"""

from __future__ import annotations

import time

import pytest

from orchestration.interfaces import ArbitrationPolicy
from orchestration.policies import (
    ConfidencePolicy,
    ConsensusPolicy,
    SafetyFirstPolicy,
    WeightedVotePolicy,
)
from tests.orchestration.conftest import learning_decision, news_signal, strategy_decision

ASSERT_SECONDS = 0.0005  # generous margin for shared/CI hardware variance


def _measure(policy: ArbitrationPolicy, n_trials: int = 10_000) -> float:
    decision_strategy = strategy_decision()
    learning = learning_decision(recommended_allocation=0.3)
    news = news_signal(sentiment_label="positive")

    start = time.perf_counter()
    for _ in range(n_trials):
        policy.arbitrate(decision_strategy, learning, news)
    return (time.perf_counter() - start) / n_trials


@pytest.mark.performance
def test_safety_first_latency_meets_target() -> None:
    elapsed_per_call = _measure(SafetyFirstPolicy())
    print(f"\nSafetyFirstPolicy.arbitrate, per-call: {elapsed_per_call * 1000:.4f}ms")
    assert elapsed_per_call < ASSERT_SECONDS


@pytest.mark.performance
def test_consensus_latency_meets_target() -> None:
    elapsed_per_call = _measure(ConsensusPolicy())
    print(f"\nConsensusPolicy.arbitrate, per-call: {elapsed_per_call * 1000:.4f}ms")
    assert elapsed_per_call < ASSERT_SECONDS


@pytest.mark.performance
def test_weighted_vote_latency_meets_target() -> None:
    elapsed_per_call = _measure(WeightedVotePolicy())
    print(f"\nWeightedVotePolicy.arbitrate, per-call: {elapsed_per_call * 1000:.4f}ms")
    assert elapsed_per_call < ASSERT_SECONDS


@pytest.mark.performance
def test_confidence_latency_meets_target() -> None:
    elapsed_per_call = _measure(ConfidencePolicy())
    print(f"\nConfidencePolicy.arbitrate, per-call: {elapsed_per_call * 1000:.4f}ms")
    assert elapsed_per_call < ASSERT_SECONDS
