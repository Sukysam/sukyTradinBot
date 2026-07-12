"""Regression tests for the `StrategyDecision` contract itself (Standards/
StrategyDecision Contract.md), distinct from `tests/strategy/`'s own unit
tests -- these exist to catch an accidental breaking change to the
contract's *shape*, not to test allocation/registry logic. If a change
here forces an edit to this file, that's a signal the change needs a new
ADR per that Standards document's own versioning policy.
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone

import pytest

from strategy.models import StrategyDecision

UTC = timezone.utc


def _decision(**overrides: object) -> StrategyDecision:
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


class TestRequiredFields:
    def test_strategy_decision_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(StrategyDecision)}
        assert field_names == {
            "timestamp",
            "symbol",
            "strategy_id",
            "regime_id",
            "allocation",
            "confidence",
            "expected_holding_period",
            "reasoning",
            "metadata",
        }


class TestSerializationRoundTrip:
    def test_decision_round_trips_through_dict(self) -> None:
        decision = _decision(metadata={"style": "growth"})
        assert StrategyDecision.from_dict(decision.to_dict()) == decision

    def test_decision_to_dict_is_json_serializable(self) -> None:
        json.dumps(_decision().to_dict())


class TestBackwardCompatibility:
    def test_construction_tolerates_unknown_metadata_keys(self) -> None:
        # Standards/StrategyDecision Contract.md ships with zero
        # guaranteed metadata keys by design (no implementation existed
        # at freeze time) -- any key must be accepted.
        _decision(metadata={"anything": "goes", "here": 123})


class TestInvariantsEnforcedAtTypeLevel:
    """The two invariants ADR-008 explicitly enforces at construction,
    not just documents: `allocation` is long-only, `reasoning` is never
    empty. These are Master Charter invariants #5 and #6 given a concrete
    shape -- a regression here is a regression in those invariants too.
    """

    @pytest.mark.parametrize("bad_allocation", [-0.01, -1.0, 1.01])
    def test_allocation_cannot_be_negative_or_exceed_one(self, bad_allocation: float) -> None:
        with pytest.raises(ValueError, match="allocation"):
            _decision(allocation=bad_allocation)

    def test_reasoning_cannot_be_empty(self) -> None:
        with pytest.raises(ValueError, match="reasoning"):
            _decision(reasoning="")

    def test_reasoning_cannot_be_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="reasoning"):
            _decision(reasoning="   \n\t")

    def test_expected_holding_period_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="expected_holding_period"):
            _decision(expected_holding_period=timedelta(0))
