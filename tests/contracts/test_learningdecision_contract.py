"""Regression tests for the `ExperienceRecord`/`LearningDecision` contract
itself (Standards/LearningDecision Contract.md), distinct from
`tests/memory/`'s own unit tests -- these exist to catch an accidental
breaking change to the contract's *shape*, not to test store/bandit/
service/evaluation logic. If a change here forces an edit to this file,
that's a signal the change needs a new ADR per that Standards document's
own versioning policy.
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone

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
        "holding_period": timedelta(days=5),
        "source_run_id": "run-1",
        "metadata": {},
    }
    defaults.update(overrides)
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


class TestRequiredFields:
    def test_experience_record_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(ExperienceRecord)}
        assert field_names == {
            "symbol",
            "strategy_id",
            "regime_id",
            "production_allocation",
            "realized_pnl",
            "realized_pnl_pct",
            "won",
            "entry_timestamp",
            "exit_timestamp",
            "holding_period",
            "source_run_id",
            "metadata",
        }

    def test_learning_decision_has_exactly_the_frozen_fields(self) -> None:
        field_names = {f.name for f in fields(LearningDecision)}
        assert field_names == {
            "timestamp",
            "symbol",
            "strategy_id",
            "regime_id",
            "production_allocation",
            "recommended_allocation",
            "confidence",
            "sample_size",
            "rationale",
            "model_version",
            "metadata",
        }


class TestSerializationRoundTrip:
    def test_experience_record_round_trips_through_dict(self) -> None:
        record = _experience(metadata={"note": "value"})
        assert ExperienceRecord.from_dict(record.to_dict()) == record

    def test_learning_decision_round_trips_through_dict(self) -> None:
        decision = _decision(metadata={"posterior_alpha": 15.0})
        assert LearningDecision.from_dict(decision.to_dict()) == decision

    def test_experience_record_to_dict_is_json_serializable(self) -> None:
        json.dumps(_experience().to_dict())

    def test_learning_decision_to_dict_is_json_serializable(self) -> None:
        json.dumps(_decision().to_dict())


class TestBackwardCompatibility:
    def test_experience_record_tolerates_unknown_metadata_keys(self) -> None:
        _experience(metadata={"anything": "goes", "here": 123})

    def test_learning_decision_tolerates_unknown_metadata_keys(self) -> None:
        _decision(metadata={"anything": "goes", "here": 123})


class TestSharedContext:
    def test_experience_record_and_learning_decision_agree_on_context_shape(self) -> None:
        # Both contracts key their learning context on the same triple --
        # (symbol, strategy_id, regime_id) -- so a caller can always pair
        # them without a schema mismatch. See ADR-016 Decision 2.
        record = _experience()
        decision = _decision()
        assert record.symbol == decision.symbol
        assert record.strategy_id == decision.strategy_id
        assert record.regime_id == decision.regime_id
        assert record.production_allocation == decision.production_allocation
