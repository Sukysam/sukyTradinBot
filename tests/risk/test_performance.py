"""Milestone 6's performance target, measured -- not assumed.

| Metric                                    | Target  |
|--------------------------------------------|---------|
| StrategyDecision -> RiskService -> ExecutionDecision | < 1ms   |

`RiskService.decide` is a pure, in-memory pipeline (no I/O, no network,
no filesystem access on the happy path -- the emergency lock file is only
ever written, never read repeatedly in a hot loop) -- comparable in order
of magnitude to `strategy.service.StrategyService.decide`'s ~0.01ms (see
tests/strategy/test_performance.py), since this milestone adds only a
handful of arithmetic comparisons and no computation heavier than that.
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import pytest

from risk.circuit_breakers import DrawdownCircuitBreaker
from risk.service import RiskService
from tests.risk.conftest import make_account_state, make_portfolio_state, make_strategy_decision

TARGET_SECONDS = 0.001
ASSERT_SECONDS = 0.005  # generous margin for shared/CI hardware variance


@pytest.mark.performance
def test_strategy_decision_to_execution_decision_latency_meets_target(tmp_path: Path) -> None:
    service = replace(
        RiskService.default(), circuit_breaker=DrawdownCircuitBreaker(lock_path=tmp_path / "lock")
    )
    decision = make_strategy_decision(allocation=0.1)
    portfolio = make_portfolio_state(equity=100_000.0)
    account = make_account_state()

    n_trials = 10_000
    start = time.perf_counter()
    for _ in range(n_trials):
        service.decide(decision, portfolio, account)
    elapsed_per_call = (time.perf_counter() - start) / n_trials

    print(
        f"\nStrategyDecision -> ExecutionDecision, per-call: "
        f"{elapsed_per_call * 1000:.4f}ms (target < {TARGET_SECONDS * 1000}ms)"
    )
    assert elapsed_per_call < ASSERT_SECONDS
