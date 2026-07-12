from __future__ import annotations

from datetime import timedelta

import pytest

from strategy.exceptions import ContractViolationError
from strategy.strategies import (
    create_bear_strategy,
    create_defensive_strategy,
    create_growth_strategy,
    create_mean_reversion_strategy,
)
from strategy.strategies._base import RegimeMappedStrategy
from tests.strategy.conftest import make_feature_vector, make_regime_state


class TestRegimeMappedStrategyValidation:
    def test_rejects_empty_strategy_id(self) -> None:
        with pytest.raises(ValueError, match="strategy_id"):
            RegimeMappedStrategy(
                strategy_id="",
                supported_regime_ids=frozenset({0}),
                base_allocation=0.5,
                expected_holding_period=timedelta(days=1),
                style="growth",
            )

    def test_allows_empty_supported_regime_ids(self) -> None:
        # legal: a pure default_strategy_id fallback, never directly matched
        strategy = RegimeMappedStrategy(
            strategy_id="fallback_only",
            supported_regime_ids=frozenset(),
            base_allocation=0.1,
            expected_holding_period=timedelta(days=1),
            style="defensive",
        )
        assert strategy.supports(0) is False

    @pytest.mark.parametrize("bad_allocation", [-0.01, 1.01])
    def test_rejects_base_allocation_out_of_bounds(self, bad_allocation: float) -> None:
        with pytest.raises(ValueError, match="base_allocation"):
            RegimeMappedStrategy(
                strategy_id="x",
                supported_regime_ids=frozenset({0}),
                base_allocation=bad_allocation,
                expected_holding_period=timedelta(days=1),
                style="growth",
            )

    def test_rejects_non_positive_expected_holding_period(self) -> None:
        with pytest.raises(ValueError, match="expected_holding_period"):
            RegimeMappedStrategy(
                strategy_id="x",
                supported_regime_ids=frozenset({0}),
                base_allocation=0.5,
                expected_holding_period=timedelta(0),
                style="growth",
            )


class TestSupports:
    def test_supports_true_for_configured_regime(self) -> None:
        strategy = create_growth_strategy("growth_v1", frozenset({0, 2}))
        assert strategy.supports(0) is True
        assert strategy.supports(2) is True

    def test_supports_false_for_unconfigured_regime(self) -> None:
        strategy = create_growth_strategy("growth_v1", frozenset({0}))
        assert strategy.supports(1) is False


class TestAllocate:
    def test_confidence_propagates_to_decision_confidence(self) -> None:
        strategy = create_growth_strategy("growth_v1", frozenset({0}))
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=0, confidence=0.73)
        decision = strategy.allocate(fv, rs)
        assert decision.confidence == 0.73

    def test_allocation_scales_linearly_with_confidence(self) -> None:
        strategy = create_growth_strategy("growth_v1", frozenset({0}), base_allocation=1.0)
        fv = make_feature_vector()
        low = strategy.allocate(fv, make_regime_state(regime_id=0, confidence=0.2))
        high = strategy.allocate(fv, make_regime_state(regime_id=0, confidence=0.9))
        assert low.allocation == pytest.approx(0.2)
        assert high.allocation == pytest.approx(0.9)
        assert low.allocation < high.allocation

    def test_zero_confidence_produces_zero_allocation(self) -> None:
        strategy = create_growth_strategy("growth_v1", frozenset({0}), base_allocation=1.0)
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=0, confidence=0.0)
        decision = strategy.allocate(fv, rs)
        assert decision.allocation == 0.0

    def test_allocation_always_within_bounds(self) -> None:
        for base in (0.0, 0.25, 0.5, 0.75, 1.0):
            strategy = create_growth_strategy("growth_v1", frozenset({0}), base_allocation=base)
            for confidence in (0.0, 0.3, 0.6, 1.0):
                fv = make_feature_vector()
                rs = make_regime_state(regime_id=0, confidence=confidence)
                decision = strategy.allocate(fv, rs)
                assert 0.0 <= decision.allocation <= 1.0

    def test_deterministic_output_for_identical_inputs(self) -> None:
        strategy = create_mean_reversion_strategy("mr_v1", frozenset({0}))
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=0, confidence=0.5)
        first = strategy.allocate(fv, rs)
        second = strategy.allocate(fv, rs)
        assert first == second

    def test_decision_carries_regime_id_and_timestamp_from_regime_state(self) -> None:
        strategy = create_growth_strategy("growth_v1", frozenset({3}))
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=3)
        decision = strategy.allocate(fv, rs)
        assert decision.regime_id == 3
        assert decision.timestamp == rs.timestamp
        assert decision.symbol == rs.symbol

    def test_allocate_does_not_require_supports_to_be_true(self) -> None:
        # A strategy used purely as a default_strategy_id fallback must be
        # callable for a regime_id it doesn't declare direct support for.
        strategy = create_defensive_strategy("defensive_v1", frozenset())
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=42, confidence=0.6)
        decision = strategy.allocate(fv, rs)
        assert decision.regime_id == 42

    def test_rejects_mismatched_symbol(self) -> None:
        strategy = create_growth_strategy("growth_v1", frozenset({0}))
        fv = make_feature_vector(symbol="AAPL")
        rs = make_regime_state(symbol="MSFT", regime_id=0)
        with pytest.raises(ContractViolationError, match="symbol"):
            strategy.allocate(fv, rs)

    def test_rejects_mismatched_timestamp(self) -> None:
        from datetime import datetime, timezone
        from datetime import timedelta as td

        strategy = create_growth_strategy("growth_v1", frozenset({0}))
        fv = make_feature_vector(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc))
        rs = make_regime_state(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + td(days=1), regime_id=0
        )
        with pytest.raises(ContractViolationError, match="timestamp"):
            strategy.allocate(fv, rs)

    def test_reasoning_is_non_empty_and_mentions_strategy(self) -> None:
        strategy = create_bear_strategy("bear_v1", frozenset({1}))
        fv = make_feature_vector()
        rs = make_regime_state(regime_id=1)
        decision = strategy.allocate(fv, rs)
        assert decision.reasoning
        assert "bear_v1" in decision.reasoning
