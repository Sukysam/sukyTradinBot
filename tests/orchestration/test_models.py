"""Tests for `orchestration.models`: `SignalInput` and `FinalDecision`'s
construction-time invariants and serialization."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orchestration.models import ArbitrationOutcome, FinalDecision, SignalInput

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _signal_input(**overrides: object) -> SignalInput:
    defaults: dict[str, object] = {
        "source": "memory",
        "considered": True,
        "agrees": True,
        "weight": 0.0,
    }
    defaults.update(overrides)
    return SignalInput(**defaults)  # type: ignore[arg-type]


def _decision(**overrides: object) -> FinalDecision:
    defaults: dict[str, object] = {
        "timestamp": T0,
        "symbol": "TEST",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "primary_allocation": 0.7,
        "final_allocation": 0.7,
        "confidence": 0.8,
        "outcome": ArbitrationOutcome.CONFIRMED,
        "learner_input": _signal_input(),
        "news_input": _signal_input(source="nlp"),
        "rationale": "strategy proposed 0.7; no disagreement",
        "metadata": {},
    }
    defaults.update(overrides)
    return FinalDecision(**defaults)  # type: ignore[arg-type]


class TestSignalInput:
    def test_valid_input_constructs(self) -> None:
        signal = _signal_input()
        assert signal.considered is True

    def test_rejects_empty_source(self) -> None:
        with pytest.raises(ValueError, match="source"):
            _signal_input(source="")

    def test_rejects_agrees_true_when_not_considered(self) -> None:
        with pytest.raises(ValueError, match="agrees must be False"):
            _signal_input(considered=False, agrees=True, weight=0.0)

    def test_rejects_nonzero_weight_when_not_considered(self) -> None:
        with pytest.raises(ValueError, match=r"weight must be 0\.0"):
            _signal_input(considered=False, agrees=False, weight=0.5)

    def test_allows_not_considered_with_false_agrees_and_zero_weight(self) -> None:
        signal = _signal_input(considered=False, agrees=False, weight=0.0)
        assert signal.considered is False

    def test_rejects_weight_out_of_bounds(self) -> None:
        with pytest.raises(ValueError, match="weight"):
            _signal_input(weight=1.5)

    def test_round_trips_through_dict(self) -> None:
        signal = _signal_input(weight=0.5, agrees=False)
        assert SignalInput.from_dict(signal.to_dict()) == signal

    def test_is_frozen(self) -> None:
        signal = _signal_input()
        with pytest.raises(AttributeError):
            signal.agrees = False  # type: ignore[misc]


class TestFinalDecision:
    def test_valid_decision_constructs(self) -> None:
        decision = _decision()
        assert decision.outcome is ArbitrationOutcome.CONFIRMED

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
    def test_rejects_primary_allocation_out_of_bounds(self, allocation: float) -> None:
        with pytest.raises(ValueError, match="primary_allocation"):
            _decision(primary_allocation=allocation, final_allocation=0.0)

    def test_rejects_final_allocation_exceeding_primary(self) -> None:
        with pytest.raises(ValueError, match="final_allocation"):
            _decision(
                primary_allocation=0.5, final_allocation=0.6, outcome=ArbitrationOutcome.CONFIRMED
            )

    def test_rejects_negative_final_allocation(self) -> None:
        with pytest.raises(ValueError, match="final_allocation"):
            _decision(primary_allocation=0.5, final_allocation=-0.1)

    def test_allows_final_allocation_equal_to_primary(self) -> None:
        decision = _decision(primary_allocation=0.5, final_allocation=0.5)
        assert decision.outcome is ArbitrationOutcome.CONFIRMED

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_rejects_confidence_out_of_bounds(self, confidence: float) -> None:
        with pytest.raises(ValueError, match="confidence"):
            _decision(confidence=confidence)

    def test_rejects_empty_rationale(self) -> None:
        with pytest.raises(ValueError, match="rationale"):
            _decision(rationale="")

    def test_rejects_whitespace_only_rationale(self) -> None:
        with pytest.raises(ValueError, match="rationale"):
            _decision(rationale="   ")

    def test_outcome_confirmed_requires_equal_allocations(self) -> None:
        with pytest.raises(ValueError, match="outcome"):
            _decision(
                primary_allocation=0.7,
                final_allocation=0.35,
                outcome=ArbitrationOutcome.CONFIRMED,
            )

    def test_outcome_suppressed_requires_zero_final_and_positive_primary(self) -> None:
        with pytest.raises(ValueError, match="outcome"):
            _decision(
                primary_allocation=0.7,
                final_allocation=0.35,
                outcome=ArbitrationOutcome.SUPPRESSED,
            )

    def test_outcome_adjusted_requires_strictly_between(self) -> None:
        with pytest.raises(ValueError, match="outcome"):
            _decision(
                primary_allocation=0.7,
                final_allocation=0.0,
                outcome=ArbitrationOutcome.ADJUSTED,
            )

    def test_accepts_consistent_suppressed_outcome(self) -> None:
        decision = _decision(
            primary_allocation=0.7,
            final_allocation=0.0,
            outcome=ArbitrationOutcome.SUPPRESSED,
        )
        assert decision.outcome is ArbitrationOutcome.SUPPRESSED

    def test_accepts_consistent_adjusted_outcome(self) -> None:
        decision = _decision(
            primary_allocation=0.7,
            final_allocation=0.35,
            outcome=ArbitrationOutcome.ADJUSTED,
        )
        assert decision.outcome is ArbitrationOutcome.ADJUSTED

    def test_zero_primary_and_final_is_confirmed_not_suppressed(self) -> None:
        decision = _decision(
            primary_allocation=0.0,
            final_allocation=0.0,
            outcome=ArbitrationOutcome.CONFIRMED,
        )
        assert decision.outcome is ArbitrationOutcome.CONFIRMED

    def test_round_trips_through_dict(self) -> None:
        decision = _decision(metadata={"note": "value"})
        assert FinalDecision.from_dict(decision.to_dict()) == decision

    def test_is_frozen(self) -> None:
        decision = _decision()
        with pytest.raises(AttributeError):
            decision.final_allocation = 0.1  # type: ignore[misc]

    def test_backward_compatible_with_unknown_metadata_keys(self) -> None:
        decision = _decision(metadata={"unexpected_future_key": 123})
        assert FinalDecision.from_dict(decision.to_dict()) == decision
