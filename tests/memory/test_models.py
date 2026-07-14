"""Tests for `memory.models`: `ExperienceRecord` and `LearningDecision`'s
construction-time invariants and serialization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memory.models import ExperienceRecord, LearningDecision

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
    if "holding_period" not in overrides:
        defaults["holding_period"] = defaults["exit_timestamp"] - defaults["entry_timestamp"]  # type: ignore[operator]
    return ExperienceRecord(**defaults)  # type: ignore[arg-type]


def _decision(**overrides: object) -> LearningDecision:
    defaults: dict[str, object] = {
        "timestamp": T0,
        "symbol": "TEST",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "production_allocation": 0.7,
        "recommended_allocation": 0.63,
        "confidence": 0.81,
        "sample_size": 14,
        "rationale": "posterior mean 0.9 across 14 samples",
        "model_version": "thompson-bandit-v1",
        "metadata": {},
    }
    defaults.update(overrides)
    return LearningDecision(**defaults)  # type: ignore[arg-type]


class TestExperienceRecord:
    def test_valid_record_constructs(self) -> None:
        record = _experience()
        assert record.symbol == "TEST"
        assert record.won is True

    def test_rejects_naive_entry_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _experience(entry_timestamp=datetime(2024, 1, 1), holding_period=timedelta(days=5))

    def test_rejects_naive_exit_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _experience(exit_timestamp=datetime(2024, 1, 6), holding_period=timedelta(days=5))

    def test_rejects_empty_symbol(self) -> None:
        with pytest.raises(ValueError, match="symbol"):
            _experience(symbol="")

    def test_rejects_empty_strategy_id(self) -> None:
        with pytest.raises(ValueError, match="strategy_id"):
            _experience(strategy_id="")

    def test_rejects_negative_regime_id(self) -> None:
        with pytest.raises(ValueError, match="regime_id"):
            _experience(regime_id=-1)

    @pytest.mark.parametrize("allocation", [-0.1, 1.1])
    def test_rejects_production_allocation_out_of_bounds(self, allocation: float) -> None:
        with pytest.raises(ValueError, match="production_allocation"):
            _experience(production_allocation=allocation)

    def test_rejects_exit_before_entry(self) -> None:
        with pytest.raises(ValueError, match="exit_timestamp must be after entry_timestamp"):
            _experience(entry_timestamp=T0, exit_timestamp=T0 - timedelta(days=1))

    def test_rejects_exit_equal_to_entry(self) -> None:
        with pytest.raises(ValueError, match="exit_timestamp must be after entry_timestamp"):
            _experience(entry_timestamp=T0, exit_timestamp=T0)

    def test_rejects_holding_period_mismatch(self) -> None:
        with pytest.raises(ValueError, match="holding_period must equal"):
            _experience(holding_period=timedelta(days=99))

    def test_rejects_won_true_with_nonpositive_pnl(self) -> None:
        with pytest.raises(ValueError, match="won"):
            _experience(realized_pnl=-5.0, won=True)

    def test_rejects_won_false_with_positive_pnl(self) -> None:
        with pytest.raises(ValueError, match="won"):
            _experience(realized_pnl=5.0, won=False)

    def test_zero_pnl_requires_won_false(self) -> None:
        record = _experience(realized_pnl=0.0, realized_pnl_pct=0.0, won=False)
        assert record.won is False

    def test_rejects_empty_source_run_id(self) -> None:
        with pytest.raises(ValueError, match="source_run_id"):
            _experience(source_run_id="")

    def test_round_trips_through_dict(self) -> None:
        record = _experience(metadata={"note": "synthetic"})
        assert ExperienceRecord.from_dict(record.to_dict()) == record

    def test_is_frozen(self) -> None:
        record = _experience()
        with pytest.raises(AttributeError):
            record.symbol = "OTHER"  # type: ignore[misc]

    def test_backward_compatible_with_unknown_metadata_keys(self) -> None:
        record = _experience(metadata={"unexpected_future_key": 123})
        data = record.to_dict()
        assert ExperienceRecord.from_dict(data) == record


class TestLearningDecision:
    def test_valid_decision_constructs(self) -> None:
        decision = _decision()
        assert decision.symbol == "TEST"
        assert decision.sample_size == 14

    def test_rejects_naive_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _decision(timestamp=datetime(2024, 1, 1))

    def test_rejects_empty_symbol(self) -> None:
        with pytest.raises(ValueError, match="symbol"):
            _decision(symbol="")

    def test_rejects_empty_strategy_id(self) -> None:
        with pytest.raises(ValueError, match="strategy_id"):
            _decision(strategy_id="")

    def test_rejects_negative_regime_id(self) -> None:
        with pytest.raises(ValueError, match="regime_id"):
            _decision(regime_id=-1)

    @pytest.mark.parametrize("allocation", [-0.1, 1.1])
    def test_rejects_production_allocation_out_of_bounds(self, allocation: float) -> None:
        with pytest.raises(ValueError, match="production_allocation"):
            _decision(production_allocation=allocation)

    @pytest.mark.parametrize("allocation", [-0.1, 1.1])
    def test_rejects_recommended_allocation_out_of_bounds(self, allocation: float) -> None:
        with pytest.raises(ValueError, match="recommended_allocation"):
            _decision(recommended_allocation=allocation)

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_rejects_confidence_out_of_bounds(self, confidence: float) -> None:
        with pytest.raises(ValueError, match="confidence"):
            _decision(confidence=confidence)

    def test_rejects_negative_sample_size(self) -> None:
        with pytest.raises(ValueError, match="sample_size"):
            _decision(sample_size=-1)

    def test_zero_sample_size_is_valid_cold_start(self) -> None:
        decision = _decision(sample_size=0, confidence=0.0)
        assert decision.sample_size == 0
        assert decision.confidence == 0.0

    def test_rejects_empty_rationale(self) -> None:
        with pytest.raises(ValueError, match="rationale"):
            _decision(rationale="")

    def test_rejects_whitespace_only_rationale(self) -> None:
        with pytest.raises(ValueError, match="rationale"):
            _decision(rationale="   ")

    def test_rejects_empty_model_version(self) -> None:
        with pytest.raises(ValueError, match="model_version"):
            _decision(model_version="")

    def test_round_trips_through_dict(self) -> None:
        decision = _decision(metadata={"posterior_alpha": 15.0, "posterior_beta": 3.0})
        assert LearningDecision.from_dict(decision.to_dict()) == decision

    def test_is_frozen(self) -> None:
        decision = _decision()
        with pytest.raises(AttributeError):
            decision.recommended_allocation = 0.5  # type: ignore[misc]

    def test_backward_compatible_with_unknown_metadata_keys(self) -> None:
        decision = _decision(metadata={"unexpected_future_key": "value"})
        data = decision.to_dict()
        assert LearningDecision.from_dict(data) == decision
