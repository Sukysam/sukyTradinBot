"""Phase C: shadow-vs-production comparison. Reads paired `LearningDecision`/
`ExperienceRecord` history and reports how the learner would have done --
never influences a real decision, never mutates the Experience Store or a
`LearningPolicy`. This module is pure comparison and reporting.

Each pair is `(decision, record)`: the `LearningDecision` generated at the
moment a real `StrategyDecision` was made, and the `ExperienceRecord` that
same trade eventually closed into. Pairing them is the caller's
responsibility -- this module only validates that a supplied pair is
internally consistent (same symbol/strategy/regime/production_allocation),
not that it was paired correctly in the first place.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from memory.models import ExperienceRecord, LearningDecision

#: Two allocations within this tolerance count as "the learner agreed
#: with production" for `agreement_rate` -- allocations are floats
#: derived from independent computations (a strategy's own logic vs. a
#: sampled Beta posterior), so exact equality would understate genuine
#: agreement.
DEFAULT_AGREEMENT_TOLERANCE = 0.05

EvaluationPair = tuple[LearningDecision, ExperienceRecord]


def _validate_pair(decision: LearningDecision, record: ExperienceRecord) -> None:
    if decision.symbol != record.symbol:
        raise ValueError(
            f"paired decision/record symbol mismatch: {decision.symbol!r} != {record.symbol!r}"
        )
    if decision.strategy_id != record.strategy_id:
        raise ValueError(
            "paired decision/record strategy_id mismatch: "
            f"{decision.strategy_id!r} != {record.strategy_id!r}"
        )
    if decision.regime_id != record.regime_id:
        raise ValueError(
            f"paired decision/record regime_id mismatch: {decision.regime_id} != {record.regime_id}"
        )
    if decision.production_allocation != record.production_allocation:
        raise ValueError(
            "paired decision/record production_allocation mismatch: "
            f"{decision.production_allocation} != {record.production_allocation}"
        )


def _simulated_pnl(decision: LearningDecision, record: ExperienceRecord) -> float:
    """`record.realized_pnl`, rescaled from `production_allocation` to
    `recommended_allocation` under a linear pnl-scales-with-position-size
    assumption -- the simplest defensible approximation available without
    a real position-sizing simulator (Milestone 8's `PortfolioEngine`
    replays fills, not counterfactual position sizes). `0.0` when
    `production_allocation` is `0.0`, since there is no realized trade to
    rescale from in that case."""
    if record.production_allocation == 0.0:
        return 0.0
    return record.realized_pnl * (decision.recommended_allocation / record.production_allocation)


def evaluate(
    pairs: Sequence[EvaluationPair], *, agreement_tolerance: float = DEFAULT_AGREEMENT_TOLERANCE
) -> dict[str, Any]:
    """Compare shadow `LearningDecision`s against the `ExperienceRecord`s
    their shadowed `StrategyDecision`s actually produced. Returns an empty-
    but-valid report (zeros, empty tuples) for an empty `pairs` -- "no
    experience yet" is a legitimate state, not an error, consistent with
    `bandit.BetaArm`'s cold-start handling."""
    if agreement_tolerance < 0.0:
        raise ValueError(f"agreement_tolerance must be >= 0, got {agreement_tolerance}")
    for decision, record in pairs:
        _validate_pair(decision, record)

    n = len(pairs)
    if n == 0:
        return {
            "n": 0,
            "agreement_rate": 0.0,
            "mean_drift": 0.0,
            "mean_absolute_drift": 0.0,
            "realized_pnl_total": 0.0,
            "simulated_pnl_total": 0.0,
            "simulated_improvement": 0.0,
            "cumulative_regret": (),
            "mean_confidence": 0.0,
        }

    ordered = sorted(pairs, key=lambda pair: pair[1].exit_timestamp)

    drifts = [
        decision.recommended_allocation - record.production_allocation
        for decision, record in ordered
    ]
    agreements = sum(1 for drift in drifts if abs(drift) <= agreement_tolerance)

    realized = [record.realized_pnl for _, record in ordered]
    simulated = [_simulated_pnl(decision, record) for decision, record in ordered]

    # Regret, in the bandit-literature sense: reward of the counterfactual
    # action (the learner's recommendation) minus reward of the chosen
    # action (production's real allocation). Positive and rising means
    # production has been leaving money on the table relative to the
    # learner; negative means production has been outperforming it.
    cumulative_regret = []
    running_total = 0.0
    for sim_pnl, real_pnl in zip(simulated, realized):
        running_total += sim_pnl - real_pnl
        cumulative_regret.append(running_total)

    realized_total = sum(realized)
    simulated_total = sum(simulated)

    return {
        "n": n,
        "agreement_rate": agreements / n,
        "mean_drift": sum(drifts) / n,
        "mean_absolute_drift": sum(abs(drift) for drift in drifts) / n,
        "realized_pnl_total": realized_total,
        "simulated_pnl_total": simulated_total,
        "simulated_improvement": simulated_total - realized_total,
        "cumulative_regret": tuple(cumulative_regret),
        "mean_confidence": sum(decision.confidence for decision, _ in ordered) / n,
    }


def generate_evaluation_report(
    pairs: Sequence[EvaluationPair], *, agreement_tolerance: float = DEFAULT_AGREEMENT_TOLERANCE
) -> str:
    """Human-readable summary of `evaluate`'s output. Deliberately plain
    text, matching `backtest.reporting.generate_report`'s minimalism --
    this is a comparison report, not a production artifact."""
    report = evaluate(pairs, agreement_tolerance=agreement_tolerance)
    lines = [
        "Memory Loop Evaluation Report",
        "=" * 30,
        f"Paired decisions: {report['n']}",
        f"Agreement rate (tolerance={agreement_tolerance}): {report['agreement_rate']:.1%}",
        f"Mean recommendation drift: {report['mean_drift']:+.4f}",
        f"Mean absolute drift: {report['mean_absolute_drift']:.4f}",
        f"Realized PnL (production): {report['realized_pnl_total']:.2f}",
        f"Simulated PnL (learner):   {report['simulated_pnl_total']:.2f}",
        f"Simulated improvement:     {report['simulated_improvement']:+.2f}",
        f"Mean learner confidence: {report['mean_confidence']:.3f}",
    ]
    if report["cumulative_regret"]:
        lines.append(f"Final cumulative regret: {report['cumulative_regret'][-1]:+.2f}")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_AGREEMENT_TOLERANCE",
    "EvaluationPair",
    "evaluate",
    "generate_evaluation_report",
]
