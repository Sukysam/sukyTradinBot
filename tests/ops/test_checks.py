"""Tests for `ops.checks`: `CallableHealthCheck` and its ten named
subsystem factory functions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common.time import FixedClock
from ops.checks import (
    CallableHealthCheck,
    configuration_check,
    execution_adapter_check,
    feature_registry_check,
    hmm_model_check,
    market_data_check,
    memory_store_check,
    model_artifact_check,
    nlp_pipeline_check,
    risk_service_check,
    strategy_registry_check,
)

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


class TestCallableHealthCheck:
    def test_name_reflects_constructor_argument(self) -> None:
        check = CallableHealthCheck("configuration", lambda: True)
        assert check.name == "configuration"

    def test_probe_returning_true_is_healthy(self) -> None:
        check = CallableHealthCheck("configuration", lambda: True, clock=FixedClock(T0))
        result = check.check()
        assert result.healthy is True
        assert result.detail == "ok"
        assert result.checked_at == T0

    def test_probe_returning_false_is_unhealthy(self) -> None:
        check = CallableHealthCheck("configuration", lambda: False, clock=FixedClock(T0))
        result = check.check()
        assert result.healthy is False
        assert result.detail == "probe returned False"

    def test_probe_raising_is_unhealthy_and_does_not_propagate(self) -> None:
        def _boom() -> bool:
            raise RuntimeError("unreachable")

        check = CallableHealthCheck("market_data", _boom, clock=FixedClock(T0))
        result = check.check()
        assert result.healthy is False
        assert "RuntimeError" in result.detail
        assert "unreachable" in result.detail

    def test_uses_system_clock_by_default(self) -> None:
        check = CallableHealthCheck("configuration", lambda: True)
        result = check.check()
        assert result.checked_at.tzinfo is not None


@pytest.mark.parametrize(
    ("factory", "expected_name"),
    [
        (configuration_check, "configuration"),
        (market_data_check, "market_data"),
        (model_artifact_check, "model_artifact"),
        (feature_registry_check, "feature_registry"),
        (hmm_model_check, "hmm_model"),
        (strategy_registry_check, "strategy_registry"),
        (risk_service_check, "risk_service"),
        (execution_adapter_check, "execution_adapter"),
        (memory_store_check, "memory_store"),
        (nlp_pipeline_check, "nlp_pipeline"),
    ],
)
class TestSubsystemCheckFactories:
    def test_name_matches_subsystem(self, factory: object, expected_name: str) -> None:
        check = factory(lambda: True)  # type: ignore[operator]
        assert check.name == expected_name

    def test_delegates_to_injected_probe(self, factory: object, expected_name: str) -> None:
        check = factory(lambda: False, clock=FixedClock(T0))  # type: ignore[operator]
        result = check.check()
        assert result.healthy is False
