"""Regression tests for the `ExecutionDecision` contract itself (Standards/
ExecutionDecision Contract.md), distinct from `tests/risk/`'s own unit
tests -- these exist to catch an accidental breaking change to the
contract's *shape*, not to test validator/sizing/circuit-breaker logic. If
a change here forces an edit to this file, that's a signal the change
needs a new ADR per that Standards document's own versioning policy.
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone

import pytest

from risk.models import DecisionType, ExecutionDecision
from strategy.models import StrategyDecision

UTC = timezone.utc


def _strategy_decision(**overrides: object) -> StrategyDecision:
    defaults: dict[str, object] = {
        "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
        "symbol": "AAPL",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "allocation": 0.5,
        "confidence": 0.8,
        "expected_holding_period": timedelta(days=5),
        "reasoning": "test reasoning",
        "metadata": {},
    }
    defaults.update(overrides)
    return StrategyDecision(**defaults)  # type: ignore[arg-type]


def _decision(**overrides: object) -> ExecutionDecision:
    strategy_decision = overrides.pop("strategy_reference", None)
    if strategy_decision is None:
        strategy_decision = _strategy_decision()
    assert isinstance(strategy_decision, StrategyDecision)
    defaults: dict[str, object] = {
        "timestamp": strategy_decision.timestamp,
        "symbol": strategy_decision.symbol,
        "approved": True,
        "approved_allocation": strategy_decision.allocation,
        "decision_type": DecisionType.APPROVED,
        "risk_adjustments": (),
        "reasoning": "Approved at full size; no limits binding.",
        "strategy_reference": strategy_decision,
        "metadata": {},
    }
    defaults.update(overrides)
    return ExecutionDecision(**defaults)  # type: ignore[arg-type]


class TestRequiredFields:
    def test_execution_decision_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(ExecutionDecision)}
        assert field_names == {
            "timestamp",
            "symbol",
            "approved",
            "approved_allocation",
            "decision_type",
            "risk_adjustments",
            "reasoning",
            "strategy_reference",
            "metadata",
        }


class TestSerializationRoundTrip:
    def test_decision_round_trips_through_dict(self) -> None:
        decision = _decision(metadata={"note": "value"})
        assert ExecutionDecision.from_dict(decision.to_dict()) == decision

    def test_decision_to_dict_is_json_serializable(self) -> None:
        json.dumps(_decision().to_dict())

    def test_rejected_decision_round_trips(self) -> None:
        decision = _decision(
            approved=False,
            approved_allocation=0.0,
            decision_type=DecisionType.REJECTED,
            risk_adjustments=("gross_exposure: too big",),
            reasoning="Rejected: gross_exposure: too big",
        )
        assert ExecutionDecision.from_dict(decision.to_dict()) == decision

    def test_reduced_decision_round_trips(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.5)
        decision = _decision(
            strategy_reference=strategy_decision,
            approved_allocation=0.3,
            decision_type=DecisionType.REDUCED,
            risk_adjustments=("exposure_capacity_sizing: reduced",),
            reasoning="Approved at reduced size (0.3 of 0.5 requested) due to: "
            "exposure_capacity_sizing: reduced",
        )
        assert ExecutionDecision.from_dict(decision.to_dict()) == decision


class TestBackwardCompatibility:
    def test_construction_tolerates_unknown_metadata_keys(self) -> None:
        # ExecutionDecision.metadata ships with zero guaranteed keys by
        # design (no implementation existed at freeze time) -- any key
        # must be accepted.
        _decision(metadata={"anything": "goes", "here": 123})


class TestInvariantsEnforcedAtTypeLevel:
    """The invariants ADR-010 explicitly enforces at construction, not
    just documents: `approved_allocation` never exceeds what the strategy
    requested, a rejection is never size- or reason-ambiguous, `reasoning`
    is never empty, and `decision_type` cannot contradict the other
    fields. These are Master Charter invariant #5's long-only guarantee
    and invariant #6's always-explainable guarantee, given a concrete
    shape one layer downstream of `StrategyDecision`.
    """

    def test_approved_allocation_cannot_exceed_strategy_reference_allocation(self) -> None:
        strategy_decision = _strategy_decision(allocation=0.5)
        with pytest.raises(ValueError, match="approved_allocation"):
            _decision(strategy_reference=strategy_decision, approved_allocation=0.6)

    def test_approved_allocation_cannot_be_negative(self) -> None:
        with pytest.raises(ValueError, match="approved_allocation"):
            _decision(
                approved=False,
                approved_allocation=-0.1,
                decision_type=DecisionType.REJECTED,
                risk_adjustments=("x",),
            )

    def test_rejected_decision_requires_zero_allocation_and_reasons(self) -> None:
        with pytest.raises(ValueError, match="risk_adjustments"):
            _decision(approved=False, approved_allocation=0.0, decision_type=DecisionType.REJECTED)

    def test_reasoning_cannot_be_empty(self) -> None:
        with pytest.raises(ValueError, match="reasoning"):
            _decision(reasoning="")

    def test_decision_type_cannot_contradict_approved(self) -> None:
        with pytest.raises(ValueError, match="decision_type"):
            _decision(approved=True, decision_type=DecisionType.REJECTED)

    def test_symbol_and_timestamp_must_match_strategy_reference(self) -> None:
        with pytest.raises(ValueError, match="symbol"):
            _decision(symbol="OTHER")
