"""Tests for `ops.diagnostics.build_diagnostic_report`."""

from __future__ import annotations

from datetime import datetime, timezone

from common.time import FixedClock
from ops.diagnostics import build_diagnostic_report
from ops.models import (
    DeploymentInfo,
    HealthCheckResult,
    PlatformHealth,
    PlatformInfo,
    RuntimeContext,
    classify_status,
)

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)
T1 = datetime(2024, 1, 2, tzinfo=UTC)


def _runtime() -> RuntimeContext:
    info = PlatformInfo(
        version="0.12.0", git_commit="abc1234", build_time=T0, python_version="3.9.6"
    )
    return RuntimeContext(platform_info=info, environment="production", startup_time=T0)


def _health() -> PlatformHealth:
    checks = (HealthCheckResult(name="configuration", healthy=True, detail="ok", checked_at=T0),)
    return PlatformHealth(
        status=classify_status(checks),
        checks=checks,
        timestamp=T0,
        version="0.12.0",
        git_commit="abc1234",
    )


def _deployment() -> DeploymentInfo:
    return DeploymentInfo(
        version="0.12.0",
        git_commit="abc1234",
        build_time=T0,
        deployment_environment="production",
        deployment_id="deploy-001",
    )


class TestBuildDiagnosticReport:
    def test_composes_runtime_and_health(self) -> None:
        runtime = _runtime()
        health = _health()
        report = build_diagnostic_report(runtime, health, clock=FixedClock(T1))
        assert report.runtime_context is runtime
        assert report.health is health
        assert report.deployment_info is None
        assert report.generated_at == T1

    def test_composes_deployment_when_given(self) -> None:
        deployment = _deployment()
        report = build_diagnostic_report(
            _runtime(), _health(), deployment=deployment, clock=FixedClock(T1)
        )
        assert report.deployment_info is deployment

    def test_uses_system_clock_by_default(self) -> None:
        report = build_diagnostic_report(_runtime(), _health())
        assert report.generated_at.tzinfo is not None
