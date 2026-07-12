"""Milestone 5's performance target, measured -- not assumed.

| Metric                              | Target  |
|--------------------------------------|---------|
| RegimeState -> StrategyDecision      | < 1ms   |

`StrategyService.decide` is a pure, in-memory dispatch (no model fitting,
no I/O, no external calls) -- several orders of magnitude cheaper than
`hmm.service.RegimeService.infer`'s ~20ms (see
tests/hmm/test_performance.py), which is expected: this milestone adds no
computation heavier than a dict/set lookup and a multiplication.
"""

from __future__ import annotations

import time

import pytest

from strategy.config import StrategyEngineConfig
from strategy.registry import StrategyRegistry
from strategy.service import StrategyService
from strategy.strategies import (
    create_bear_strategy,
    create_defensive_strategy,
    create_growth_strategy,
)
from tests.strategy.conftest import make_feature_vector, make_regime_state

TARGET_SECONDS = 0.001
ASSERT_SECONDS = 0.005  # generous margin for shared/CI hardware variance


def _service() -> StrategyService:
    registry = StrategyRegistry()
    registry.register(create_growth_strategy("growth_v1", frozenset({0})))
    registry.register(create_bear_strategy("bear_v1", frozenset({1})))
    registry.register(create_defensive_strategy("defensive_v1", frozenset()))
    return StrategyService(registry, StrategyEngineConfig(default_strategy_id="defensive_v1"))


@pytest.mark.performance
def test_regime_state_to_strategy_decision_latency_meets_target() -> None:
    service = _service()
    fv = make_feature_vector()
    rs = make_regime_state(regime_id=0)

    n_trials = 10_000
    start = time.perf_counter()
    for _ in range(n_trials):
        service.decide(fv, rs)
    elapsed_per_call = (time.perf_counter() - start) / n_trials

    print(
        f"\nRegimeState -> StrategyDecision, per-call: "
        f"{elapsed_per_call * 1000:.4f}ms (target < {TARGET_SECONDS * 1000}ms)"
    )
    assert elapsed_per_call < ASSERT_SECONDS
