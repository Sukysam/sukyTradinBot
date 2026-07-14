"""Tests for `ops.logging`: `log_health_status` and `log_alert`."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from ops.alerts import Alert, AlertSeverity
from ops.logging import log_alert, log_health_status
from ops.models import HealthCheckResult, PlatformHealth, classify_status

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _result(**overrides: object) -> HealthCheckResult:
    defaults: dict[str, object] = {
        "name": "configuration",
        "healthy": True,
        "detail": "ok",
        "checked_at": T0,
    }
    defaults.update(overrides)
    return HealthCheckResult(**defaults)  # type: ignore[arg-type]


def _health(checks: tuple[HealthCheckResult, ...]) -> PlatformHealth:
    return PlatformHealth(
        status=classify_status(checks),
        checks=checks,
        timestamp=T0,
        version="0.12.0",
        git_commit="abc1234",
    )


class TestLogHealthStatus:
    def test_logs_at_info_with_structured_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = logging.getLogger("test.ops.health")
        health = _health((_result(healthy=True), _result(healthy=False, name="market_data")))
        with caplog.at_level(logging.INFO, logger="test.ops.health"):
            log_health_status(logger, health)
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "INFO"
        assert record.event == "health_status"  # type: ignore[attr-defined]
        assert record.status == "degraded"  # type: ignore[attr-defined]
        assert record.failing_checks == ["market_data"]  # type: ignore[attr-defined]
        assert record.version == "0.12.0"  # type: ignore[attr-defined]
        assert record.git_commit == "abc1234"  # type: ignore[attr-defined]

    def test_healthy_report_has_no_failing_checks(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = logging.getLogger("test.ops.health")
        with caplog.at_level(logging.INFO, logger="test.ops.health"):
            log_health_status(logger, _health((_result(),)))
        assert caplog.records[0].failing_checks == []  # type: ignore[attr-defined]


class TestLogAlert:
    def test_logs_at_warning_with_structured_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = logging.getLogger("test.ops.alerts")
        alert = Alert(
            name="platform_unhealthy",
            severity=AlertSeverity.CRITICAL,
            detail="failing checks: configuration",
            triggered_at=T0,
        )
        with caplog.at_level(logging.WARNING, logger="test.ops.alerts"):
            log_alert(logger, alert)
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "WARNING"
        assert record.event == "alert_fired"  # type: ignore[attr-defined]
        assert record.alert == "platform_unhealthy"  # type: ignore[attr-defined]
        assert record.severity == "critical"  # type: ignore[attr-defined]
        assert record.detail == "failing checks: configuration"  # type: ignore[attr-defined]
