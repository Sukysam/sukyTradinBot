"""`WeightedVotePolicy` -- blends a fixed vote weight per source into a
continuous multiplier, rather than SafetyFirst/Consensus's discrete
one-disagreement/two-disagreement thresholds. The primary
`StrategyDecision` always votes "agree" with weight `strategy_weight`;
each considered advisory signal votes 1.0 (agrees) or 0.0 (disagrees)
with its own configured weight. `final_allocation = primary_allocation *
weighted_average(votes)`.

Structurally can never fully suppress a decision as long as
`strategy_weight > 0` (enforced at construction) -- the strategy's own
vote always pulls the weighted average above zero. That's a deliberate,
named difference from `SafetyFirstPolicy`/`ConsensusPolicy`, not an
oversight: this policy models "advisory signals nudge conviction," not
"advisory signals can veto it."
"""

from __future__ import annotations

from dataclasses import dataclass, field

from memory.models import LearningDecision
from nlp.models import NewsSignal
from orchestration.config import OrchestrationConfig
from orchestration.models import FinalDecision, SignalInput
from orchestration.signals import (
    classify_outcome,
    learner_considered_and_agrees,
    news_considered_and_agrees,
    validate_context,
)
from strategy.models import StrategyDecision

_MEMORY_SOURCE = "memory"
_NLP_SOURCE = "nlp"

DEFAULT_STRATEGY_WEIGHT = 1.0
DEFAULT_LEARNER_WEIGHT = 0.5
DEFAULT_NEWS_WEIGHT = 0.5


def _build_rationale(
    strategy_decision: StrategyDecision,
    learning_decision: LearningDecision | None,
    news_signal: NewsSignal | None,
    learner_input: SignalInput,
    news_input: SignalInput,
    multiplier: float,
    outcome: str,
) -> str:
    parts = [f"[weighted_vote] strategy proposed allocation {strategy_decision.allocation:.3f}"]
    if learner_input.considered:
        assert learning_decision is not None
        verb = "agrees" if learner_input.agrees else "disagrees"
        parts.append(
            f"learner recommended {learning_decision.recommended_allocation:.3f} "
            f"({verb}, weight={learner_input.weight:.2f})"
        )
    else:
        parts.append("no learner signal considered")
    if news_input.considered:
        assert news_signal is not None
        verb = "agrees" if news_input.agrees else "disagrees"
        parts.append(
            f"news sentiment {news_signal.sentiment_label} "
            f"({verb}, weight={news_input.weight:.2f})"
        )
    else:
        parts.append("no news signal considered")
    parts.append(f"weighted vote multiplier {multiplier:.3f}; outcome: {outcome}")
    return "; ".join(parts)


@dataclass
class WeightedVotePolicy:
    config: OrchestrationConfig = field(default_factory=OrchestrationConfig)
    strategy_weight: float = DEFAULT_STRATEGY_WEIGHT
    learner_weight: float = DEFAULT_LEARNER_WEIGHT
    news_weight: float = DEFAULT_NEWS_WEIGHT

    def __post_init__(self) -> None:
        if self.strategy_weight <= 0.0:
            raise ValueError(f"strategy_weight must be > 0, got {self.strategy_weight}")
        if self.learner_weight < 0.0:
            raise ValueError(f"learner_weight must be >= 0, got {self.learner_weight}")
        if self.news_weight < 0.0:
            raise ValueError(f"news_weight must be >= 0, got {self.news_weight}")

    def arbitrate(
        self,
        strategy_decision: StrategyDecision,
        learning_decision: LearningDecision | None,
        news_signal: NewsSignal | None,
    ) -> FinalDecision:
        validate_context(strategy_decision, learning_decision, news_signal)

        primary_allocation = strategy_decision.allocation
        learner_considered, learner_agrees = learner_considered_and_agrees(
            strategy_decision, learning_decision, self.config.agreement_tolerance
        )
        news_considered, news_agrees = news_considered_and_agrees(strategy_decision, news_signal)

        votes = [(self.strategy_weight, 1.0)]
        learner_weight = 0.0
        if learner_considered:
            learner_weight = self.learner_weight
            votes.append((learner_weight, 1.0 if learner_agrees else 0.0))
        news_weight = 0.0
        if news_considered:
            news_weight = self.news_weight
            votes.append((news_weight, 1.0 if news_agrees else 0.0))

        total_weight = sum(weight for weight, _ in votes)
        multiplier = sum(weight * vote for weight, vote in votes) / total_weight

        final_allocation = 0.0 if primary_allocation == 0.0 else primary_allocation * multiplier
        outcome = classify_outcome(primary_allocation, final_allocation)

        learner_input = SignalInput(
            source=_MEMORY_SOURCE,
            considered=learner_considered,
            agrees=learner_agrees,
            weight=(learner_weight / total_weight) if learner_considered else 0.0,
        )
        news_input = SignalInput(
            source=_NLP_SOURCE,
            considered=news_considered,
            agrees=news_agrees,
            weight=(news_weight / total_weight) if news_considered else 0.0,
        )

        confidence = strategy_decision.confidence * multiplier

        return FinalDecision(
            timestamp=strategy_decision.timestamp,
            symbol=strategy_decision.symbol,
            strategy_id=strategy_decision.strategy_id,
            regime_id=strategy_decision.regime_id,
            primary_allocation=primary_allocation,
            final_allocation=final_allocation,
            confidence=confidence,
            outcome=outcome,
            learner_input=learner_input,
            news_input=news_input,
            rationale=_build_rationale(
                strategy_decision,
                learning_decision,
                news_signal,
                learner_input,
                news_input,
                multiplier,
                outcome.value,
            ),
            metadata={},
        )


__all__ = [
    "DEFAULT_LEARNER_WEIGHT",
    "DEFAULT_NEWS_WEIGHT",
    "DEFAULT_STRATEGY_WEIGHT",
    "WeightedVotePolicy",
]
