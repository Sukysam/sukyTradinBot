"""Tests for `execution.stop_loss`: `ATRStopPolicy` and
`FixedPercentPolicy`."""

from __future__ import annotations

import pytest

from execution.stop_loss import ATRStopPolicy, FixedPercentPolicy
from tests.execution.conftest import make_execution_context, make_feature_snapshot


class TestATRStopPolicy:
    def test_stop_is_reference_price_minus_multiplier_times_atr(self) -> None:
        policy = ATRStopPolicy(atr_multiplier=2.0)
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot(atr_14=3.0)
        assert policy.compute_stop_loss(context, snapshot) == pytest.approx(94.0)

    def test_larger_multiplier_produces_a_lower_stop(self) -> None:
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot(atr_14=3.0)
        tight = ATRStopPolicy(atr_multiplier=1.0).compute_stop_loss(context, snapshot)
        wide = ATRStopPolicy(atr_multiplier=3.0).compute_stop_loss(context, snapshot)
        assert wide < tight

    def test_zero_atr_produces_stop_equal_to_reference_price(self) -> None:
        policy = ATRStopPolicy()
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot(atr_14=0.0)
        assert policy.compute_stop_loss(context, snapshot) == 100.0

    def test_rejects_non_positive_multiplier(self) -> None:
        with pytest.raises(ValueError, match="atr_multiplier"):
            ATRStopPolicy(atr_multiplier=0.0)

    def test_name_is_stable(self) -> None:
        assert ATRStopPolicy().name == "atr_stop"


class TestFixedPercentPolicy:
    def test_stop_is_reference_price_times_one_minus_percent(self) -> None:
        policy = FixedPercentPolicy(percent=0.05)
        context = make_execution_context(reference_price=100.0)
        snapshot = make_feature_snapshot()
        assert policy.compute_stop_loss(context, snapshot) == pytest.approx(95.0)

    def test_ignores_feature_snapshot(self) -> None:
        policy = FixedPercentPolicy(percent=0.02)
        context = make_execution_context(reference_price=100.0)
        low_atr = policy.compute_stop_loss(context, make_feature_snapshot(atr_14=0.0))
        high_atr = policy.compute_stop_loss(context, make_feature_snapshot(atr_14=50.0))
        assert low_atr == high_atr

    @pytest.mark.parametrize("bad_percent", [0.0, 1.0, -0.1, 1.5])
    def test_rejects_percent_outside_open_unit_interval(self, bad_percent: float) -> None:
        with pytest.raises(ValueError, match="percent"):
            FixedPercentPolicy(percent=bad_percent)

    def test_name_is_stable(self) -> None:
        assert FixedPercentPolicy().name == "fixed_percent_stop"
