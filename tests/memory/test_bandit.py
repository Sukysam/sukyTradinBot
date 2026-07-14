"""Tests for `memory.bandit`: `context_key`, `BetaArm`'s posterior
mechanics, and `ThompsonSamplingPolicy`'s `LearningPolicy` implementation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from random import Random

import pytest

from memory.bandit import BetaArm, ThompsonSamplingPolicy, context_key
from memory.config import MemoryConfig
from memory.models import ExperienceRecord

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


class TestContextKey:
    def test_combines_strategy_and_regime(self) -> None:
        assert context_key("growth_v1", 2) == "growth_v1|2"

    def test_different_regimes_produce_different_keys(self) -> None:
        assert context_key("growth_v1", 1) != context_key("growth_v1", 2)

    def test_different_strategies_produce_different_keys(self) -> None:
        assert context_key("growth_v1", 1) != context_key("bear_v1", 1)


class TestBetaArm:
    def test_default_prior_is_uniform(self) -> None:
        arm = BetaArm()
        assert arm.alpha == 1.0
        assert arm.beta == 1.0
        assert arm.posterior_mean == pytest.approx(0.5)

    def test_starts_with_zero_sample_size(self) -> None:
        assert BetaArm().sample_size == 0

    def test_rejects_nonpositive_prior_alpha(self) -> None:
        with pytest.raises(ValueError, match="prior_alpha"):
            BetaArm(prior_alpha=0.0)

    def test_rejects_nonpositive_prior_beta(self) -> None:
        with pytest.raises(ValueError, match="prior_beta"):
            BetaArm(prior_beta=-1.0)

    def test_update_win_increments_alpha(self) -> None:
        arm = BetaArm()
        arm.update(won=True)
        assert arm.alpha == 2.0
        assert arm.beta == 1.0

    def test_update_loss_increments_beta(self) -> None:
        arm = BetaArm()
        arm.update(won=False)
        assert arm.alpha == 1.0
        assert arm.beta == 2.0

    def test_sample_size_counts_all_updates(self) -> None:
        arm = BetaArm()
        for won in (True, False, True, True, False):
            arm.update(won)
        assert arm.sample_size == 5

    def test_posterior_mean_shifts_toward_wins(self) -> None:
        arm = BetaArm()
        for _ in range(10):
            arm.update(won=True)
        assert arm.posterior_mean > 0.9

    def test_posterior_mean_shifts_toward_losses(self) -> None:
        arm = BetaArm()
        for _ in range(10):
            arm.update(won=False)
        assert arm.posterior_mean < 0.1

    def test_sample_is_deterministic_given_seeded_rng(self) -> None:
        arm = BetaArm()
        arm.update(won=True)
        first = arm.sample(Random(42))
        second = arm.sample(Random(42))
        assert first == second

    def test_sample_is_bounded_zero_one(self) -> None:
        arm = BetaArm()
        rng = Random(7)
        for _ in range(50):
            value = arm.sample(rng)
            assert 0.0 <= value <= 1.0


class TestThompsonSamplingPolicy:
    def test_update_creates_arm_lazily(self) -> None:
        policy = ThompsonSamplingPolicy()
        policy.update(_experience(strategy_id="growth_v1", regime_id=0, won=True))
        arm = policy._arm_for("growth_v1", 0)
        assert arm.sample_size == 1

    def test_arms_are_independent_per_context(self) -> None:
        policy = ThompsonSamplingPolicy()
        policy.update(_experience(strategy_id="growth_v1", regime_id=0, won=True))
        policy.update(_experience(strategy_id="bear_v1", regime_id=0, won=False))
        assert policy._arm_for("growth_v1", 0).alpha == 2.0
        assert policy._arm_for("bear_v1", 0).beta == 2.0

    def test_recommend_cold_start_has_zero_confidence(self) -> None:
        policy = ThompsonSamplingPolicy()
        decision = policy.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=Random(1),
        )
        assert decision.sample_size == 0
        assert decision.confidence == 0.0

    def test_recommend_is_deterministic_given_seeded_rng(self) -> None:
        policy = ThompsonSamplingPolicy()
        policy.update(_experience(won=True))
        first = policy.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=Random(99),
        )
        policy2 = ThompsonSamplingPolicy()
        policy2.update(_experience(won=True))
        second = policy2.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=Random(99),
        )
        assert first == second

    def test_recommended_allocation_never_exceeds_production(self) -> None:
        policy = ThompsonSamplingPolicy()
        rng = Random(3)
        for _ in range(20):
            decision = policy.recommend(
                timestamp=T0,
                symbol="TEST",
                strategy_id="growth_v1",
                regime_id=0,
                production_allocation=0.7,
                rng=rng,
            )
            assert 0.0 <= decision.recommended_allocation <= 0.7

    def test_recommend_confidence_increases_with_sample_size(self) -> None:
        policy = ThompsonSamplingPolicy(config=MemoryConfig(confidence_smoothing=10.0))
        rng = Random(5)
        low = policy.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=rng,
        )
        for _ in range(50):
            policy.update(_experience(won=True))
        high = policy.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=rng,
        )
        assert high.confidence > low.confidence

    def test_rationale_mentions_context(self) -> None:
        policy = ThompsonSamplingPolicy()
        decision = policy.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=2,
            production_allocation=0.7,
            rng=Random(1),
        )
        assert "growth_v1" in decision.rationale
        assert "regime=2" in decision.rationale

    def test_model_version_reflects_config(self) -> None:
        policy = ThompsonSamplingPolicy(config=MemoryConfig(model_version="custom-v2"))
        decision = policy.recommend(
            timestamp=T0,
            symbol="TEST",
            strategy_id="growth_v1",
            regime_id=0,
            production_allocation=0.7,
            rng=Random(1),
        )
        assert decision.model_version == "custom-v2"
