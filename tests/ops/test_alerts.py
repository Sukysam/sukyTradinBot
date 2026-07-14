"""Tests for `ops.alerts`: `CallableAlertRule`, the built-in rule
factories, and `evaluate_alerts`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common.time import FixedClock
from ops.alerts import (
    Alert,
    AlertSeverity,
    CallableAlertRule,
    degraded_platform_rule,
    evaluate_alerts,
    unhealthy_platform_rule,
)
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


class TestAlert:
    def test_rejects_naive_triggered_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            Alert(
                name="platform_unhealthy",
                severity=AlertSeverity.CRITICAL,
                detail="failing checks: configuration",
                triggered_at=datetime(2024, 1, 1),
            )

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            Alert(name="", severity=AlertSeverity.CRITICAL, detail="x", triggered_at=T0)

    def test_rejects_empty_detail(self) -> None:
        with pytest.raises(ValueError, match="detail"):
            Alert(
                name="platform_unhealthy",
                severity=AlertSeverity.CRITICAL,
                detail="",
                triggered_at=T0,
            )


class TestCallableAlertRule:
    def test_returns_none_when_predicate_false(self) -> None:
        rule = CallableAlertRule(
            "always_false",
            AlertSeverity.WARNING,
            predicate=lambda health: False,
            detail=lambda health: "unreachable",
        )
        assert rule.evaluate(_health((_result(),))) is None

    def test_returns_alert_when_predicate_true(self) -> None:
        rule = CallableAlertRule(
            "always_true",
            AlertSeverity.CRITICAL,
            predicate=lambda health: True,
            detail=lambda health: "fired",
            clock=FixedClock(T0),
        )
        alert = rule.evaluate(_health((_result(),)))
        assert alert is not None
        assert alert.name == "always_true"
        assert alert.severity is AlertSeverity.CRITICAL
        assert alert.detail == "fired"
        assert alert.triggered_at == T0

    def test_name_property_reflects_constructor_argument(self) -> None:
        rule = CallableAlertRule(
            "custom_rule",
            AlertSeverity.WARNING,
            predicate=lambda health: False,
            detail=lambda health: "",
        )
        assert rule.name == "custom_rule"


class TestUnhealthyPlatformRule:
    def test_fires_when_all_checks_fail(self) -> None:
        rule = unhealthy_platform_rule(clock=FixedClock(T0))
        alert = rule.evaluate(_health((_result(healthy=False),)))
        assert alert is not None
        assert alert.severity is AlertSeverity.CRITICAL
        assert "configuration" in alert.detail

    def test_does_not_fire_when_degraded(self) -> None:
        rule = unhealthy_platform_rule()
        health = _health((_result(healthy=True), _result(healthy=False, name="market_data")))
        assert rule.evaluate(health) is None

    def test_does_not_fire_when_healthy(self) -> None:
        rule = unhealthy_platform_rule()
        assert rule.evaluate(_health((_result(),))) is None


class TestDegradedPlatformRule:
    def test_fires_when_partially_failing(self) -> None:
        rule = degraded_platform_rule(clock=FixedClock(T0))
        health = _health((_result(healthy=True), _result(healthy=False, name="market_data")))
        alert = rule.evaluate(health)
        assert alert is not None
        assert alert.severity is AlertSeverity.WARNING
        assert "market_data" in alert.detail

    def test_does_not_fire_when_healthy(self) -> None:
        rule = degraded_platform_rule()
        assert rule.evaluate(_health((_result(),))) is None

    def test_does_not_fire_when_fully_unhealthy(self) -> None:
        rule = degraded_platform_rule()
        assert rule.evaluate(_health((_result(healthy=False),))) is None


class TestEvaluateAlerts:
    def test_returns_empty_tuple_when_no_rule_fires(self) -> None:
        health = _health((_result(),))
        alerts = evaluate_alerts(health, [unhealthy_platform_rule(), degraded_platform_rule()])
        assert alerts == ()

    def test_returns_only_firing_rules_in_order(self) -> None:
        health = _health((_result(healthy=False),))
        alerts = evaluate_alerts(health, [degraded_platform_rule(), unhealthy_platform_rule()])
        assert [alert.name for alert in alerts] == ["platform_unhealthy"]
