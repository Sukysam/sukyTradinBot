"""Milestone 9's performance targets, measured -- not assumed.

| Metric                                  | Target  |
|------------------------------------------|---------|
| Experience insert (`InMemoryExperienceStore.append`) | < 0.1ms |
| Bandit update (`ThompsonSamplingPolicy.update`)       | < 0.1ms |
| Recommendation (`ThompsonSamplingPolicy.recommend`)   | < 0.1ms |

All three are pure in-memory, no I/O -- comparable in spirit to
`tests/risk/test_performance.py`'s `RiskService.decide` measurement.
`JsonlExperienceStore.append`'s file I/O is deliberately not benchmarked
here: its latency is dominated by filesystem/OS behavior, not this
package's own logic, the same reason `backtest`'s benchmark doesn't
separately measure disk-write cost anywhere in its pipeline.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from random import Random

import pytest

from memory.bandit import ThompsonSamplingPolicy
from memory.models import ExperienceRecord
from memory.store import InMemoryExperienceStore

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)
ASSERT_SECONDS = 0.0005  # generous margin for shared/CI hardware variance


def _record(index: int) -> ExperienceRecord:
    return ExperienceRecord(
        symbol="TEST",
        strategy_id="growth_v1",
        regime_id=0,
        production_allocation=0.7,
        realized_pnl=100.0,
        realized_pnl_pct=0.1,
        won=True,
        entry_timestamp=T0,
        exit_timestamp=T0 + timedelta(days=5),
        holding_period=timedelta(days=5),
        source_run_id=f"run-{index}",
        metadata={},
    )


@pytest.mark.performance
def test_experience_insert_latency_meets_target() -> None:
    store = InMemoryExperienceStore()
    n_trials = 10_000
    records = [_record(i) for i in range(n_trials)]

    start = time.perf_counter()
    for record in records:
        store.append(record)
    elapsed_per_call = (time.perf_counter() - start) / n_trials

    print(f"\nExperience insert, per-call: {elapsed_per_call * 1000:.4f}ms")
    assert elapsed_per_call < ASSERT_SECONDS


@pytest.mark.performance
def test_bandit_update_latency_meets_target() -> None:
    policy = ThompsonSamplingPolicy()
    n_trials = 10_000
    records = [_record(i) for i in range(n_trials)]

    start = time.perf_counter()
    for record in records:
        policy.update(record)
    elapsed_per_call = (time.perf_counter() - start) / n_trials

    print(f"\nBandit update, per-call: {elapsed_per_call * 1000:.4f}ms")
    assert elapsed_per_call < ASSERT_SECONDS


@pytest.mark.performance
def test_recommend_latency_meets_target() -> None:
    policy = ThompsonSamplingPolicy()
    for record in (_record(i) for i in range(50)):
        policy.update(record)
    rng = Random(7)

    n_trials = 10_000
    start = time.perf_counter()
    for _ in range(n_trials):
        policy.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=rng,
        )
    elapsed_per_call = (time.perf_counter() - start) / n_trials

    print(f"\nRecommendation generation, per-call: {elapsed_per_call * 1000:.4f}ms")
    assert elapsed_per_call < ASSERT_SECONDS
