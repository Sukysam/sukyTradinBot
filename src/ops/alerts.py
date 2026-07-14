"""Alert rule evaluation over `PlatformHealth`.

One generic `CallableAlertRule` wraps a predicate/detail pair, plus two
named built-in rule factories -- the same "one generic wrapper, named
factories" pattern `ops.checks` already established for subsystem
health probes, applied here to alert rules for the same reason: DRY
evaluation logic, discoverable, individually-testable named rules.
Alerting reads only `PlatformHealth` -- it never recomputes health
independently.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from common.interfaces import Clock
from common.time import SystemClock, require_utc
from ops.models import HealthStatus, PlatformHealth

_DEFAULT_CLOCK: Clock = SystemClock()


class AlertSeverity(str, Enum):
    """Closed set of alert severities. `WARNING` for `DEGRADED`
    platform health, `CRITICAL` for `UNHEALTHY` -- mirrors
    `HealthStatus`'s own three-way classification one level up."""

    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Alert:
    """One fired alert. `detail` is never empty -- the same "never
    produce an unexplained result" principle `HealthCheckResult.detail`
    already carries, applied here because an alert that can't say *why*
    it fired isn't actionable for whoever is paged."""

    name: str
    severity: AlertSeverity
    detail: str
    triggered_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.triggered_at, "triggered_at")
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.detail.strip():
            raise ValueError("detail must not be empty")


@runtime_checkable
class AlertRule(Protocol):
    """Evaluates one `PlatformHealth` report, returning an `Alert` if
    the rule's condition is met, `None` otherwise."""

    @property
    def name(self) -> str: ...

    def evaluate(self, health: PlatformHealth) -> Alert | None: ...


@dataclass(frozen=True)
class CallableAlertRule:
    """An `AlertRule` backed by an injected `predicate`/`detail` pair --
    `predicate` decides whether the rule fires, `detail` renders the
    `Alert.detail` message when it does. Never constructed with a
    real-world side effect inside `predicate`; it only reads `health`."""

    _name: str
    severity: AlertSeverity
    predicate: Callable[[PlatformHealth], bool]
    detail: Callable[[PlatformHealth], str]
    clock: Clock = field(default_factory=SystemClock)

    @property
    def name(self) -> str:
        return self._name

    def evaluate(self, health: PlatformHealth) -> Alert | None:
        if not self.predicate(health):
            return None
        return Alert(
            name=self._name,
            severity=self.severity,
            detail=self.detail(health),
            triggered_at=self.clock.now(),
        )


def _failing_check_names(health: PlatformHealth) -> str:
    return ", ".join(check.name for check in health.checks if not check.healthy)


def unhealthy_platform_rule(*, clock: Clock = _DEFAULT_CLOCK) -> CallableAlertRule:
    """Fires `CRITICAL` when `PlatformHealth.status` is `UNHEALTHY`."""
    return CallableAlertRule(
        "platform_unhealthy",
        AlertSeverity.CRITICAL,
        predicate=lambda health: health.status is HealthStatus.UNHEALTHY,
        detail=lambda health: f"failing checks: {_failing_check_names(health)}",
        clock=clock,
    )


def degraded_platform_rule(*, clock: Clock = _DEFAULT_CLOCK) -> CallableAlertRule:
    """Fires `WARNING` when `PlatformHealth.status` is `DEGRADED`."""
    return CallableAlertRule(
        "platform_degraded",
        AlertSeverity.WARNING,
        predicate=lambda health: health.status is HealthStatus.DEGRADED,
        detail=lambda health: f"failing checks: {_failing_check_names(health)}",
        clock=clock,
    )


def evaluate_alerts(health: PlatformHealth, rules: Sequence[AlertRule]) -> tuple[Alert, ...]:
    """Evaluate every rule in `rules` against `health`, returning the
    `Alert`s that fired, in rule order."""
    alerts: list[Alert] = []
    for rule in rules:
        alert = rule.evaluate(health)
        if alert is not None:
            alerts.append(alert)
    return tuple(alerts)


__all__ = [
    "Alert",
    "AlertRule",
    "AlertSeverity",
    "CallableAlertRule",
    "degraded_platform_rule",
    "evaluate_alerts",
    "unhealthy_platform_rule",
]
