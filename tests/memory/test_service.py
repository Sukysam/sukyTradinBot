"""Tests for `memory.service.MemoryService` -- the orchestration layer
wiring an `ExperienceStore` and a `LearningPolicy` together."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from random import Random

from memory.bandit import ThompsonSamplingPolicy
from memory.models import ExperienceRecord
from memory.service import MemoryService
from memory.store import InMemoryExperienceStore

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _experience(**overrides: object) -> ExperienceRecord:
    defaults: dict[str, object] = {
        "symbol": "TEST",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "production_allocation": 0.7,
        "realized_pnl": 100.0,
        "realized_pnl_pct": 0.1,
        "won": True,
        "entry_timestamp": T0,
        "exit_timestamp": T0 + timedelta(days=5),
        "source_run_id": "run-1",
        "metadata": {},
    }
    defaults.update(overrides)
    if "won" in overrides and "realized_pnl" not in overrides:
        defaults["realized_pnl"] = 100.0 if overrides["won"] else -100.0
        defaults["realized_pnl_pct"] = 0.1 if overrides["won"] else -0.1
    if "holding_period" not in overrides:
        defaults["holding_period"] = defaults["exit_timestamp"] - defaults["entry_timestamp"]  # type: ignore[operator]
    return ExperienceRecord(**defaults)  # type: ignore[arg-type]


def _service() -> MemoryService:
    return MemoryService(store=InMemoryExperienceStore(), policy=ThompsonSamplingPolicy())


class TestMemoryService:
    def test_record_experience_appends_to_store(self) -> None:
        service = _service()
        record = _experience()
        service.record_experience(record)
        assert len(service.store) == 1
        assert service.store.for_context(strategy_id="growth_v1", regime_id=0) == (record,)

    def test_record_experience_updates_policy(self) -> None:
        service = _service()
        service.record_experience(_experience(won=True))
        recommendation = service.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=Random(1),
        )
        assert recommendation.sample_size == 1

    def test_recommend_never_mutates_store(self) -> None:
        service = _service()
        service.record_experience(_experience())
        before = len(service.store)
        service.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=Random(1),
        )
        assert len(service.store) == before

    def test_recommend_does_not_require_prior_experience(self) -> None:
        service = _service()
        recommendation = service.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=Random(1),
        )
        assert recommendation.sample_size == 0
        assert recommendation.confidence == 0.0

    def test_separate_contexts_do_not_interfere(self) -> None:
        service = _service()
        service.record_experience(_experience(strategy_id="growth_v1", regime_id=0, won=True))
        service.record_experience(_experience(strategy_id="bear_v1", regime_id=0, won=False))
        growth = service.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=Random(1),
        )
        bear = service.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="bear_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=Random(1),
        )
        assert growth.sample_size == 1
        assert bear.sample_size == 1
