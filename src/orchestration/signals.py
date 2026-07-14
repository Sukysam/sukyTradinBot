"""Shared helpers used by every `orchestration.interfaces.ArbitrationPolicy`
implementation: context validation and considered/agrees classification
for the two advisory signal types. Kept separate from any one policy so
Phase B's multiple policies don't each reimplement -- and risk silently
diverging on -- the same agreement logic. `orchestration.models.
ArbitrationOutcome` classification is also centralized here for the same
reason.
"""

from __future__ import annotations

from memory.models import LearningDecision
from nlp.models import NewsSignal
from orchestration.exceptions import MismatchedSignalError
from orchestration.models import ArbitrationOutcome
from strategy.models import StrategyDecision


def require_matching_learner_context(
    strategy_decision: StrategyDecision, learning_decision: LearningDecision
) -> None:
    if learning_decision.symbol != strategy_decision.symbol:
        raise MismatchedSignalError(
            f"learning_decision.symbol {learning_decision.symbol!r} does not match "
            f"strategy_decision.symbol {strategy_decision.symbol!r}"
        )
    if learning_decision.strategy_id != strategy_decision.strategy_id:
        raise MismatchedSignalError(
            f"learning_decision.strategy_id {learning_decision.strategy_id!r} does not "
            f"match strategy_decision.strategy_id {strategy_decision.strategy_id!r}"
        )
    if learning_decision.regime_id != strategy_decision.regime_id:
        raise MismatchedSignalError(
            f"learning_decision.regime_id {learning_decision.regime_id!r} does not match "
            f"strategy_decision.regime_id {strategy_decision.regime_id!r}"
        )


def require_matching_news_context(
    strategy_decision: StrategyDecision, news_signal: NewsSignal
) -> None:
    if strategy_decision.symbol not in news_signal.symbols:
        raise MismatchedSignalError(
            f"strategy_decision.symbol {strategy_decision.symbol!r} not found in "
            f"news_signal.symbols {news_signal.symbols!r}"
        )


def validate_context(
    strategy_decision: StrategyDecision,
    learning_decision: LearningDecision | None,
    news_signal: NewsSignal | None,
) -> None:
    """Convenience wrapper calling both context checks -- every policy's
    `arbitrate` starts with this."""
    if learning_decision is not None:
        require_matching_learner_context(strategy_decision, learning_decision)
    if news_signal is not None:
        require_matching_news_context(strategy_decision, news_signal)


def learner_considered_and_agrees(
    strategy_decision: StrategyDecision,
    learning_decision: LearningDecision | None,
    tolerance: float,
) -> tuple[bool, bool]:
    if learning_decision is None:
        return False, False
    if strategy_decision.allocation == 0.0:
        return True, True  # nothing to disagree about
    agrees = (
        abs(learning_decision.recommended_allocation - strategy_decision.allocation) <= tolerance
    )
    return True, agrees


def news_considered_and_agrees(
    strategy_decision: StrategyDecision, news_signal: NewsSignal | None
) -> tuple[bool, bool]:
    if news_signal is None:
        return False, False
    if strategy_decision.allocation == 0.0:
        return True, True  # nothing to disagree about
    agrees = news_signal.sentiment_label != "negative"
    return True, agrees


def classify_outcome(primary_allocation: float, final_allocation: float) -> ArbitrationOutcome:
    if final_allocation == primary_allocation:
        return ArbitrationOutcome.CONFIRMED
    if final_allocation == 0.0:
        return ArbitrationOutcome.SUPPRESSED
    return ArbitrationOutcome.ADJUSTED


__all__ = [
    "classify_outcome",
    "learner_considered_and_agrees",
    "news_considered_and_agrees",
    "require_matching_learner_context",
    "require_matching_news_context",
    "validate_context",
]
