"""Regression tests for the `FinalDecision`/`SignalInput` contract itself
(Standards/FinalDecision Contract.md), distinct from `tests/orchestration/`'s
own unit tests -- these exist to catch an accidental breaking change to
the contract's *shape*, not to test arbitration/policy/evaluation logic.
If a change here forces an edit to this file, that's a signal the change
needs a new ADR per that Standards document's own versioning policy.
"""

from __future__ import annotations

import json
from dataclasses import fields
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


class TestRequiredFields:
    def test_signal_input_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(SignalInput)}
        assert field_names == {"source", "considered", "agrees", "weight"}

    def test_final_decision_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(FinalDecision)}
        assert field_names == {
            "timestamp",
            "symbol",
            "strategy_id",
            "regime_id",
            "primary_allocation",
            "final_allocation",
            "confidence",
            "outcome",
            "learner_input",
            "news_input",
            "rationale",
            "metadata",
        }

    def test_arbitration_outcome_has_exactly_the_frozen_values(self) -> None:
        assert {member.value for member in ArbitrationOutcome} == {
            "confirmed",
            "adjusted",
            "suppressed",
        }


class TestSerializationRoundTrip:
    def test_signal_input_round_trips_through_dict(self) -> None:
        signal = _signal_input(weight=0.5, agrees=False)
        assert SignalInput.from_dict(signal.to_dict()) == signal

    def test_final_decision_round_trips_through_dict(self) -> None:
        decision = _decision(metadata={"note": "value"})
        assert FinalDecision.from_dict(decision.to_dict()) == decision

    def test_to_dict_is_json_serializable(self) -> None:
        json.dumps(_decision().to_dict())


class TestBackwardCompatibility:
    def test_construction_tolerates_unknown_metadata_keys(self) -> None:
        _decision(metadata={"anything": "goes", "here": 123})


class TestAllocationBound:
    def test_final_allocation_never_exceeds_primary(self) -> None:
        # Contract-level invariant: this is what makes advisory signals
        # structurally unable to manufacture conviction the primary
        # StrategyDecision never had. See ADR-020 Decision 1.
        with pytest.raises(ValueError, match="final_allocation"):
            _decision(primary_allocation=0.5, final_allocation=0.6)
