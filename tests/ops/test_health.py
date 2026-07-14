"""Tests for `ops.health`: `evaluate_health` and `require_healthy`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common.time import FixedClock
from ops.checks import configuration_check, market_data_check
from ops.exceptions import UnhealthyPlatformError
from ops.health import evaluate_health, require_healthy
from ops.models import HealthStatus

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


class TestEvaluateHealth:
    def test_all_healthy_checks_produce_healthy_report(self) -> None:
        checks = [configuration_check(lambda: True), market_data_check(lambda: True)]
        health = evaluate_health(
            checks, version="0.12.0", git_commit="abc1234", clock=FixedClock(T0)
        )
        assert health.status is HealthStatus.HEALTHY
        assert len(health.checks) == 2
        assert health.version == "0.12.0"
        assert health.git_commit == "abc1234"
        assert health.timestamp == T0

    def test_one_failing_check_produces_degraded_report(self) -> None:
        checks = [configuration_check(lambda: True), market_data_check(lambda: False)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        assert health.status is HealthStatus.DEGRADED

    def test_all_failing_checks_produce_unhealthy_report(self) -> None:
        checks = [configuration_check(lambda: False), market_data_check(lambda: False)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        assert health.status is HealthStatus.UNHEALTHY

    def test_uses_system_clock_by_default(self) -> None:
        checks = [configuration_check(lambda: True)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        assert health.timestamp.tzinfo is not None


class TestRequireHealthy:
    def test_healthy_report_does_not_raise(self) -> None:
        checks = [configuration_check(lambda: True)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        require_healthy(health)

    def test_degraded_report_raises_with_failing_check_names(self) -> None:
        checks = [configuration_check(lambda: True), market_data_check(lambda: False)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        with pytest.raises(UnhealthyPlatformError, match="market_data"):
            require_healthy(health)

    def test_unhealthy_report_raises(self) -> None:
        checks = [configuration_check(lambda: False)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        with pytest.raises(UnhealthyPlatformError, match="unhealthy"):
            require_healthy(health)
