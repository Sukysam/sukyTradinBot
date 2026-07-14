"""`SafetyFirstPolicy` -- the default arbitration policy, and Phase A's
original single deterministic rule, now behind `ArbitrationPolicy`.
One disagreeing advisory signal cuts `final_allocation` by
`config.disagreement_penalty`; two disagreeing signals suppress the
decision entirely. The most conservative of the four policies: any
double disagreement always suppresses, regardless of how confident
either advisory signal actually was.
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


def _weight_for(considered: bool, agrees: bool, disagreement_count: int, penalty: float) -> float:
    if not considered or agrees:
        return 0.0
    if disagreement_count >= 2:
        return 0.5
    return penalty


def _build_rationale(
    strategy_decision: StrategyDecision,
    learning_decision: LearningDecision | None,
    news_signal: NewsSignal | None,
    learner_input: SignalInput,
    news_input: SignalInput,
    outcome: str,
) -> str:
    parts = [f"[safety_first] strategy proposed allocation {strategy_decision.allocation:.3f}"]
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
    parts.append(f"outcome: {outcome}")
    return "; ".join(parts)


@dataclass
class SafetyFirstPolicy:
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

        disagreement_count = sum(
            1
            for considered, agrees in (
                (learner_considered, learner_agrees),
                (news_considered, news_agrees),
            )
            if considered and not agrees
        )

        if primary_allocation == 0.0 or disagreement_count >= 2:
            final_allocation = 0.0
        elif disagreement_count == 1:
            final_allocation = primary_allocation * (1.0 - self.config.disagreement_penalty)
        else:
            final_allocation = primary_allocation

        outcome = classify_outcome(primary_allocation, final_allocation)

        learner_input = SignalInput(
            source=_MEMORY_SOURCE,
            considered=learner_considered,
            agrees=learner_agrees,
            weight=_weight_for(
                learner_considered,
                learner_agrees,
                disagreement_count,
                self.config.disagreement_penalty,
            ),
        )
        news_input = SignalInput(
            source=_NLP_SOURCE,
            considered=news_considered,
            agrees=news_agrees,
            weight=_weight_for(
                news_considered, news_agrees, disagreement_count, self.config.disagreement_penalty
            ),
        )

        confidence = (
            strategy_decision.confidence * (final_allocation / primary_allocation)
            if primary_allocation > 0.0
            else strategy_decision.confidence
        )

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


__all__ = ["SafetyFirstPolicy"]
