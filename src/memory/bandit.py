"""`ThompsonSamplingPolicy` -- Phase B's `memory.interfaces.LearningPolicy`
implementation. Adapts the contextual multi-armed bandit already validated
by `regime-trader/core/learning_engine.py` (see
docs/engineering-handbook/Architecture/Reinforcement Learning Memory
Loop.md): Thompson Sampling over a Beta(alpha, beta) posterior, one
independent arm per `(strategy_id, regime_id)` context. Deliberately not
LightGBM -- see ADR-016's Alternatives Considered for why a contextual
bandit is the right starting point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from random import Random

from memory.config import MemoryConfig
from memory.models import ExperienceRecord, LearningDecision


def context_key(strategy_id: str, regime_id: int) -> str:
    """The bucketed learning context this policy generalizes over --
    deliberately `(strategy_id, regime_id)` only, narrower than the
    legacy `(strategy, regime_label, rsi_bucket)`. See ADR-016's
    "Deliberate scope boundary" for why: fewer dimensions means more
    samples accumulate per arm, sooner."""
    return f"{strategy_id}|{regime_id}"


@dataclass
class BetaArm:
    """One context's Beta(alpha, beta) posterior over "does this context
    produce a winning trade." Deliberately mutable -- like
    `backtest.portfolio.PortfolioEngine`, this is the one place in this
    package with genuine state to hold across calls, per Master Charter
    Section 10 ("reach for a class only when there is genuine state to
    hold across calls")."""

    prior_alpha: float = 1.0
    prior_beta: float = 1.0
    alpha: float = field(init=False)
    beta: float = field(init=False)

    def __post_init__(self) -> None:
        if self.prior_alpha <= 0.0:
            raise ValueError(f"prior_alpha must be > 0, got {self.prior_alpha}")
        if self.prior_beta <= 0.0:
            raise ValueError(f"prior_beta must be > 0, got {self.prior_beta}")
        self.alpha = self.prior_alpha
        self.beta = self.prior_beta

    def update(self, won: bool) -> None:
        """`alpha += 1` on a win, `beta += 1` on a loss -- the same
        update rule `learning_engine.BetaArm.update` already uses."""
        if won:
            self.alpha += 1.0
        else:
            self.beta += 1.0

    @property
    def posterior_mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def sample_size(self) -> int:
        """Number of observed outcomes folded into this arm since
        construction -- `(alpha - prior_alpha) + (beta - prior_beta)`,
        always a non-negative integer since `update` adds exactly `1.0`
        to one side per call."""
        return round((self.alpha - self.prior_alpha) + (self.beta - self.prior_beta))

    def sample(self, rng: Random) -> float:
        """Draw from the full Beta posterior (Thompson Sampling) rather
        than always returning `posterior_mean` -- see the Architecture
        doc's "Why Thompson Sampling, not greedy exploitation" for why an
        under-observed arm still needs to be explored. `rng` is always
        caller-supplied for determinism -- never a module-level global."""
        return rng.betavariate(self.alpha, self.beta)


@dataclass
class ThompsonSamplingPolicy:
    """`memory.interfaces.LearningPolicy` implementation: one `BetaArm`
    per `(strategy_id, regime_id)` context, created lazily on first use."""

    config: MemoryConfig = field(default_factory=MemoryConfig)
    _arms: dict[str, BetaArm] = field(default_factory=dict, init=False)

    def _arm_for(self, strategy_id: str, regime_id: int) -> BetaArm:
        key = context_key(strategy_id, regime_id)
        if key not in self._arms:
            self._arms[key] = BetaArm(
                prior_alpha=self.config.prior_alpha, prior_beta=self.config.prior_beta
            )
        return self._arms[key]

    def update(self, record: ExperienceRecord) -> None:
        arm = self._arm_for(record.strategy_id, record.regime_id)
        arm.update(record.won)

    def recommend(
        self,
        *,
        timestamp: datetime,
        symbol: str,
        strategy_id: str,
        regime_id: int,
        production_allocation: float,
        rng: Random,
    ) -> LearningDecision:
        arm = self._arm_for(strategy_id, regime_id)
        sampled_weight = arm.sample(rng)
        # `sampled_weight` is a Beta-distributed draw in [0, 1] and
        # `production_allocation` is already bounded to [0, 1], so their
        # product is too -- the bandit only ever scales production's own
        # allocation down or (rarely, for a very strong posterior) close
        # to unchanged, never proposes a larger allocation than
        # production chose. min/max clamp only guards float edge cases.
        recommended_allocation = min(1.0, max(0.0, production_allocation * sampled_weight))
        sample_size = arm.sample_size
        confidence = sample_size / (sample_size + self.config.confidence_smoothing)
        wins = arm.alpha - arm.prior_alpha
        losses = arm.beta - arm.prior_beta
        rationale = (
            f"context (strategy={strategy_id}, regime={regime_id}) has "
            f"{wins:.0f} win(s) / {losses:.0f} loss(es) across {sample_size} sample(s); "
            f"posterior mean {arm.posterior_mean:.3f}, sampled weight {sampled_weight:.3f}"
        )
        return LearningDecision(
            timestamp=timestamp,
            symbol=symbol,
            strategy_id=strategy_id,
            regime_id=regime_id,
            production_allocation=production_allocation,
            recommended_allocation=recommended_allocation,
            confidence=confidence,
            sample_size=sample_size,
            rationale=rationale,
            model_version=self.config.model_version,
            metadata={
                "posterior_alpha": arm.alpha,
                "posterior_beta": arm.beta,
                "sampled_weight": sampled_weight,
            },
        )


__all__ = ["BetaArm", "ThompsonSamplingPolicy", "context_key"]
