"""Tests for `memory.evaluation` -- Phase C's shadow-vs-production
comparison. No production influence is exercised or possible here: these
functions only read paired `LearningDecision`/`ExperienceRecord` history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memory.evaluation import evaluate, generate_evaluation_report
from memory.models import ExperienceRecord, LearningDecision

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _decision(**overrides: object) -> LearningDecision:
    defaults: dict[str, object] = {
        "timestamp": T0,
        "symbol": "TEST",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "production_allocation": 0.7,
        "recommended_allocation": 0.63,
        "confidence": 0.8,
        "sample_size": 14,
        "rationale": "posterior mean 0.9",
        "model_version": "thompson-bandit-v1",
        "metadata": {},
    }
    defaults.update(overrides)
    return LearningDecision(**defaults)  # type: ignore[arg-type]


def _record(**overrides: object) -> ExperienceRecord:
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
    if "holding_period" not in overrides:
        defaults["holding_period"] = defaults["exit_timestamp"] - defaults["entry_timestamp"]  # type: ignore[operator]
    return ExperienceRecord(**defaults)  # type: ignore[arg-type]


class TestEvaluateEmptyInput:
    def test_returns_zeroed_report(self) -> None:
        report = evaluate([])
        assert report["n"] == 0
        assert report["agreement_rate"] == 0.0
        assert report["cumulative_regret"] == ()


class TestEvaluatePairValidation:
    def test_rejects_symbol_mismatch(self) -> None:
        with pytest.raises(ValueError, match="symbol mismatch"):
            evaluate([(_decision(symbol="A"), _record(symbol="B"))])

    def test_rejects_strategy_id_mismatch(self) -> None:
        with pytest.raises(ValueError, match="strategy_id mismatch"):
            evaluate([(_decision(strategy_id="growth_v1"), _record(strategy_id="bear_v1"))])

    def test_rejects_regime_id_mismatch(self) -> None:
        with pytest.raises(ValueError, match="regime_id mismatch"):
            evaluate([(_decision(regime_id=0), _record(regime_id=1))])

    def test_rejects_production_allocation_mismatch(self) -> None:
        with pytest.raises(ValueError, match="production_allocation mismatch"):
            evaluate([(_decision(production_allocation=0.7), _record(production_allocation=0.5))])

    def test_rejects_negative_agreement_tolerance(self) -> None:
        with pytest.raises(ValueError, match="agreement_tolerance"):
            evaluate([], agreement_tolerance=-0.1)


class TestEvaluate:
    def test_agreement_rate_counts_close_recommendations(self) -> None:
        pairs = [
            (_decision(recommended_allocation=0.71), _record()),  # within default tolerance
            (_decision(recommended_allocation=0.20), _record()),  # far off
        ]
        report = evaluate(pairs, agreement_tolerance=0.05)
        assert report["agreement_rate"] == 0.5

    def test_mean_drift_is_signed(self) -> None:
        pairs = [(_decision(recommended_allocation=0.5), _record(production_allocation=0.7))]
        report = evaluate(pairs)
        assert report["mean_drift"] == pytest.approx(-0.2)

    def test_mean_absolute_drift_is_unsigned(self) -> None:
        pairs = [(_decision(recommended_allocation=0.5), _record(production_allocation=0.7))]
        report = evaluate(pairs)
        assert report["mean_absolute_drift"] == pytest.approx(0.2)

    def test_simulated_pnl_scales_linearly_with_allocation(self) -> None:
        decision = _decision(production_allocation=0.5, recommended_allocation=0.25)
        record = _record(production_allocation=0.5, realized_pnl=100.0)
        report = evaluate([(decision, record)])
        assert report["simulated_pnl_total"] == pytest.approx(50.0)

    def test_simulated_pnl_is_zero_when_production_allocation_is_zero(self) -> None:
        decision = _decision(production_allocation=0.0, recommended_allocation=0.0)
        record = _record(
            production_allocation=0.0, realized_pnl=0.0, realized_pnl_pct=0.0, won=False
        )
        report = evaluate([(decision, record)])
        assert report["simulated_pnl_total"] == 0.0

    def test_simulated_improvement_is_difference_of_totals(self) -> None:
        decision = _decision(production_allocation=0.5, recommended_allocation=1.0)
        record = _record(production_allocation=0.5, realized_pnl=100.0)
        report = evaluate([(decision, record)])
        assert report["simulated_improvement"] == pytest.approx(100.0)

    def test_cumulative_regret_is_ordered_by_exit_timestamp(self) -> None:
        earlier = (
            _decision(production_allocation=0.5, recommended_allocation=1.0),
            _record(
                production_allocation=0.5,
                realized_pnl=100.0,
                exit_timestamp=T0 + timedelta(days=1),
            ),
        )
        later = (
            _decision(production_allocation=0.5, recommended_allocation=0.5),
            _record(
                production_allocation=0.5,
                realized_pnl=100.0,
                exit_timestamp=T0 + timedelta(days=2),
            ),
        )
        # Passed in reverse order -- evaluate() must sort by exit_timestamp.
        report = evaluate([later, earlier])
        assert len(report["cumulative_regret"]) == 2
        assert report["cumulative_regret"][0] == pytest.approx(100.0)
        assert report["cumulative_regret"][1] == pytest.approx(100.0)

    def test_mean_confidence_averages_decision_confidence(self) -> None:
        pairs = [
            (_decision(confidence=0.2), _record()),
            (_decision(confidence=0.8), _record()),
        ]
        report = evaluate(pairs)
        assert report["mean_confidence"] == pytest.approx(0.5)


class TestGenerateEvaluationReport:
    def test_report_is_nonempty_string(self) -> None:
        report = generate_evaluation_report([(_decision(), _record())])
        assert isinstance(report, str)
        assert "Memory Loop Evaluation Report" in report

    def test_report_includes_key_metrics(self) -> None:
        report = generate_evaluation_report([(_decision(), _record())])
        assert "Agreement rate" in report
        assert "Mean recommendation drift" in report
        assert "Simulated improvement" in report

    def test_report_handles_empty_input(self) -> None:
        report = generate_evaluation_report([])
        assert "Paired decisions: 0" in report
