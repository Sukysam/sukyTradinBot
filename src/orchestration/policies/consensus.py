"""`ConsensusPolicy` -- stricter than `SafetyFirstPolicy`: *any* considered
advisory signal disagreeing suppresses the decision entirely. Models
"unless every available signal agrees, don't act" rather than tolerating
a single dissent.
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


def _build_rationale(
    strategy_decision: StrategyDecision,
    learning_decision: LearningDecision | None,
    news_signal: NewsSignal | None,
    learner_input: SignalInput,
    news_input: SignalInput,
    outcome: str,
) -> str:
    parts = [f"[consensus] strategy proposed allocation {strategy_decision.allocation:.3f}"]
    if learner_input.considered:
        assert learning_decision is not None
        verb = "agrees" if learner_input.agrees else "disagrees"
        parts.append(f"learner recommended {learning_decision.recommended_allocation:.3f} ({verb})")
    else:
        parts.append("no learner signal considered")
    if news_input.considered:
        assert news_signal is not None
        verb = "agrees" if news_input.agrees else "disagrees"
        parts.append(f"news sentiment {news_signal.sentiment_label} ({verb})")
    else:
        parts.append("no news signal considered")
    parts.append(f"outcome: {outcome} (consensus requires unanimous agreement)")
    return "; ".join(parts)


@dataclass
class ConsensusPolicy:
    config: OrchestrationConfig = field(default_factory=OrchestrationConfig)

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

        any_disagreement = (learner_considered and not learner_agrees) or (
            news_considered and not news_agrees
        )
        final_allocation = (
            0.0 if (primary_allocation == 0.0 or any_disagreement) else primary_allocation
        )

        outcome = classify_outcome(primary_allocation, final_allocation)

        learner_input = SignalInput(
            source=_MEMORY_SOURCE,
            considered=learner_considered,
            agrees=learner_agrees,
            weight=1.0 if (learner_considered and not learner_agrees) else 0.0,
        )
        news_input = SignalInput(
            source=_NLP_SOURCE,
            considered=news_considered,
            agrees=news_agrees,
            weight=1.0 if (news_considered and not news_agrees) else 0.0,
        )

        confidence = strategy_decision.confidence if final_allocation == primary_allocation else 0.0

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
                outcome.value,
            ),
            metadata={},
        )


__all__ = ["ConsensusPolicy"]
