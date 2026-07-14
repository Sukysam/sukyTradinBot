"""`ConfidencePolicy` -- scales `final_allocation` by how confident the
advisory signals are *relative to the strategy's own confidence*,
independent of directional agreement. `SignalInput.agrees` is still
populated (using the same direction-based check every other policy
uses) for audit consistency, but it does not drive this policy's
allocation math -- confidence does. A highly confident but disagreeing
news signal and a barely-confident agreeing one are treated very
differently here, unlike `SafetyFirstPolicy`/`ConsensusPolicy`, which
only look at agreement direction and ignore confidence entirely.
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


def _news_model_confidence(news_signal: NewsSignal) -> float:
    """FinBERT's own confidence in its sentiment call -- the highest of
    the three softmax probabilities, independent of which label it
    picked or whether that label agrees with the primary decision."""
    return max(
        news_signal.sentiment_positive,
        news_signal.sentiment_negative,
        news_signal.sentiment_neutral,
    )


def _build_rationale(
    strategy_decision: StrategyDecision,
    learning_decision: LearningDecision | None,
    news_signal: NewsSignal | None,
    learner_input: SignalInput,
    news_input: SignalInput,
    multiplier: float,
    outcome: str,
) -> str:
    parts = [
        f"[confidence] strategy proposed allocation {strategy_decision.allocation:.3f} "
        f"at confidence {strategy_decision.confidence:.3f}"
    ]
    if learner_input.considered:
        assert learning_decision is not None
        parts.append(f"learner confidence {learning_decision.confidence:.3f}")
    else:
        parts.append("no learner signal considered")
    if news_input.considered:
        assert news_signal is not None
        parts.append(f"news model confidence {_news_model_confidence(news_signal):.3f}")
    else:
        parts.append("no news signal considered")
    parts.append(f"confidence multiplier {multiplier:.3f}; outcome: {outcome}")
    return "; ".join(parts)


@dataclass
class ConfidencePolicy:
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

        advisory_confidences = []
        if learning_decision is not None:
            advisory_confidences.append(learning_decision.confidence)
        if news_signal is not None:
            advisory_confidences.append(_news_model_confidence(news_signal))

        if advisory_confidences and strategy_decision.confidence > 0.0:
            average_advisory_confidence = sum(advisory_confidences) / len(advisory_confidences)
            multiplier = min(1.0, average_advisory_confidence / strategy_decision.confidence)
        elif advisory_confidences:
            multiplier = 0.0
        else:
            multiplier = 1.0

        final_allocation = 0.0 if primary_allocation == 0.0 else primary_allocation * multiplier
        outcome = classify_outcome(primary_allocation, final_allocation)

        learner_input = SignalInput(
            source=_MEMORY_SOURCE,
            considered=learner_considered,
            agrees=learner_agrees,
            weight=(1.0 - multiplier) if learner_considered else 0.0,
        )
        news_input = SignalInput(
            source=_NLP_SOURCE,
            considered=news_considered,
            agrees=news_agrees,
            weight=(1.0 - multiplier) if news_considered else 0.0,
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


__all__ = ["ConfidencePolicy"]
