"""Phase C: read-only cross-signal reporting. Answers "how often did the
platform's signals agree, and how much did the orchestrator actually
change?" -- these metrics only become meaningful once multiple signal
sources exist to compare, which is why they're Milestone 11's job, not
Milestone 9's or 10's own (per direct product-owner review). Never
influences a decision, never mutates a `FinalDecision`, an
`ArbitrationPolicy`, or any upstream signal source.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from memory.models import LearningDecision
from nlp.models import NewsSignal
from orchestration.exceptions import OrchestrationError
from orchestration.models import ArbitrationOutcome, FinalDecision

EvaluationRecord = tuple[FinalDecision, "LearningDecision | None", "NewsSignal | None"]


def _validate_record(
    decision: FinalDecision,
    learning_decision: LearningDecision | None,
    news_signal: NewsSignal | None,
) -> None:
    if learning_decision is not None and (
        learning_decision.symbol != decision.symbol
        or learning_decision.strategy_id != decision.strategy_id
        or learning_decision.regime_id != decision.regime_id
    ):
        raise OrchestrationError(
            f"paired learning_decision context does not match decision for "
            f"symbol {decision.symbol!r}"
        )
    if news_signal is not None and decision.symbol not in news_signal.symbols:
        raise OrchestrationError(
            f"paired news_signal does not cover decision symbol {decision.symbol!r}"
        )


def evaluate(records: Sequence[EvaluationRecord]) -> dict[str, Any]:
    """Reads paired `(FinalDecision, LearningDecision | None, NewsSignal |
    None)` history -- the raw advisory inputs are needed alongside each
    `FinalDecision` because `SignalInput` alone doesn't carry the
    magnitude a divergence metric needs. Returns an empty-but-valid
    report (zeros) for an empty `records` -- "nothing arbitrated yet" is
    a legitimate state, not an error, consistent with every other
    evaluation module in this handbook."""
    if not records:
        return {
            "n": 0,
            "agreement_rate": 0.0,
            "signal_conflict_rate": 0.0,
            "strategy_vs_learner_divergence": 0.0,
            "news_alignment": 0.0,
            "orchestration_confidence": 0.0,
            "override_frequency": 0.0,
        }

    for decision, learning_decision, news_signal in records:
        _validate_record(decision, learning_decision, news_signal)

    n = len(records)

    confirmed = sum(
        1 for decision, _, _ in records if decision.outcome is ArbitrationOutcome.CONFIRMED
    )
    agreement_rate = confirmed / n
    override_frequency = 1.0 - agreement_rate

    both_considered = [
        decision
        for decision, _, _ in records
        if decision.learner_input.considered and decision.news_input.considered
    ]
    conflicts = sum(
        1
        for decision in both_considered
        if decision.learner_input.agrees != decision.news_input.agrees
    )
    signal_conflict_rate = conflicts / len(both_considered) if both_considered else 0.0

    divergences = [
        abs(decision.primary_allocation - learning_decision.recommended_allocation)
        for decision, learning_decision, _ in records
        if learning_decision is not None
    ]
    strategy_vs_learner_divergence = sum(divergences) / len(divergences) if divergences else 0.0

    news_paired_decisions = [decision for decision, _, news in records if news is not None]
    news_agree_count = sum(1 for decision in news_paired_decisions if decision.news_input.agrees)
    news_alignment = news_agree_count / len(news_paired_decisions) if news_paired_decisions else 0.0

    orchestration_confidence = sum(decision.confidence for decision, _, _ in records) / n

    return {
        "n": n,
        "agreement_rate": agreement_rate,
        "signal_conflict_rate": signal_conflict_rate,
        "strategy_vs_learner_divergence": strategy_vs_learner_divergence,
        "news_alignment": news_alignment,
        "orchestration_confidence": orchestration_confidence,
        "override_frequency": override_frequency,
    }


def generate_evaluation_report(records: Sequence[EvaluationRecord]) -> str:
    """Human-readable summary of `evaluate`'s output. Deliberately plain
    text, matching `backtest.reporting.generate_report` and `memory.
    evaluation.generate_evaluation_report`'s minimalism."""
    report = evaluate(records)
    lines = [
        "Signal Orchestration Evaluation Report",
        "=" * 39,
        f"Decisions: {report['n']}",
        f"Agreement rate: {report['agreement_rate']:.1%}",
        f"Override frequency: {report['override_frequency']:.1%}",
        f"Signal conflict rate (learner vs news): {report['signal_conflict_rate']:.1%}",
        f"Strategy vs learner divergence: {report['strategy_vs_learner_divergence']:.4f}",
        f"News alignment: {report['news_alignment']:.1%}",
        f"Mean orchestration confidence: {report['orchestration_confidence']:.3f}",
    ]
    return "\n".join(lines)


__all__ = ["EvaluationRecord", "evaluate", "generate_evaluation_report"]
