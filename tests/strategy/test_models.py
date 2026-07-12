from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from strategy.models import StrategyDecision

UTC = timezone.utc
NAIVE = datetime(2024, 1, 1)
AWARE = datetime(2024, 1, 1, tzinfo=UTC)
NON_UTC = datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=-5)))


def _decision(**overrides: object) -> StrategyDecision:
    defaults: dict[str, object] = {
        "timestamp": AWARE,
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


def test_valid_decision_constructs() -> None:
    decision = _decision()
    assert decision.symbol == "AAPL"
    assert decision.strategy_id == "growth_v1"


def test_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _decision(timestamp=NAIVE)


def test_rejects_non_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="UTC"):
        _decision(timestamp=NON_UTC)


def test_rejects_empty_symbol() -> None:
    with pytest.raises(ValueError, match="symbol"):
        _decision(symbol="")


def test_rejects_empty_strategy_id() -> None:
    with pytest.raises(ValueError, match="strategy_id"):
        _decision(strategy_id="")


def test_rejects_negative_regime_id() -> None:
    with pytest.raises(ValueError, match="regime_id"):
        _decision(regime_id=-1)


@pytest.mark.parametrize("bad_allocation", [-0.01, 1.01])
def test_rejects_allocation_out_of_bounds(bad_allocation: float) -> None:
    with pytest.raises(ValueError, match="allocation"):
        _decision(allocation=bad_allocation)


@pytest.mark.parametrize("bad_confidence", [-0.01, 1.01])
def test_rejects_confidence_out_of_bounds(bad_confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        _decision(confidence=bad_confidence)


def test_allocation_boundary_values_accepted() -> None:
    _decision(allocation=0.0)
    _decision(allocation=1.0)


@pytest.mark.parametrize("bad_period", [timedelta(0), timedelta(seconds=-1)])
def test_rejects_non_positive_expected_holding_period(bad_period: timedelta) -> None:
    with pytest.raises(ValueError, match="expected_holding_period"):
        _decision(expected_holding_period=bad_period)


def test_rejects_empty_reasoning() -> None:
    with pytest.raises(ValueError, match="reasoning"):
        _decision(reasoning="")


def test_rejects_whitespace_only_reasoning() -> None:
    with pytest.raises(ValueError, match="reasoning"):
        _decision(reasoning="   ")


def test_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    decision = _decision()
    with pytest.raises(FrozenInstanceError):
        decision.allocation = 0.9  # type: ignore[misc]


def test_round_trips_through_dict() -> None:
    decision = _decision(metadata={"style": "growth", "base_allocation": 1.0})
    assert StrategyDecision.from_dict(decision.to_dict()) == decision


def test_to_dict_is_json_serializable() -> None:
    import json

    decision = _decision()
    json.dumps(decision.to_dict())
