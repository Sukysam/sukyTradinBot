"""Tests for `ops.models`: `HealthCheckResult`, `PlatformHealth`,
`PlatformInfo`, `RuntimeContext`, `DeploymentInfo`, and
`DiagnosticReport`'s construction-time invariants, serialization, and
`classify_status`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ops.models import (
    DeploymentInfo,
    DiagnosticReport,
    HealthCheckResult,
    HealthStatus,
    PlatformHealth,
    PlatformInfo,
    RuntimeContext,
    classify_status,
)

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


def _info(**overrides: object) -> PlatformInfo:
    defaults: dict[str, object] = {
        "version": "0.12.0",
        "git_commit": "abc1234",
        "build_time": T0,
        "python_version": "3.9.6",
    }
    defaults.update(overrides)
    return PlatformInfo(**defaults)  # type: ignore[arg-type]


def _context(**overrides: object) -> RuntimeContext:
    defaults: dict[str, object] = {
        "platform_info": _info(),
        "environment": "production",
        "startup_time": T0,
    }
    defaults.update(overrides)
    return RuntimeContext(**defaults)  # type: ignore[arg-type]


def _deployment(**overrides: object) -> DeploymentInfo:
    defaults: dict[str, object] = {
        "version": "0.12.0",
        "git_commit": "abc1234",
        "build_time": T0,
        "deployment_environment": "production",
        "deployment_id": "deploy-001",
    }
    defaults.update(overrides)
    return DeploymentInfo(**defaults)  # type: ignore[arg-type]


def _health(**overrides: object) -> PlatformHealth:
    checks = overrides.pop("checks", (_result(),))
    defaults: dict[str, object] = {
        "status": classify_status(checks),  # type: ignore[arg-type]
        "checks": checks,
        "timestamp": T0,
        "version": "0.12.0",
        "git_commit": "abc1234",
    }
    defaults.update(overrides)
    return PlatformHealth(**defaults)  # type: ignore[arg-type]


def _diagnostic(**overrides: object) -> DiagnosticReport:
    defaults: dict[str, object] = {
        "runtime_context": _context(),
        "health": _health(),
        "deployment_info": None,
        "generated_at": T0,
    }
    defaults.update(overrides)
    return DiagnosticReport(**defaults)  # type: ignore[arg-type]


class TestHealthCheckResult:
    def test_valid_result_constructs(self) -> None:
        result = _result()
        assert result.healthy is True

    def test_rejects_naive_checked_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _result(checked_at=datetime(2024, 1, 1))

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            _result(name="")

    def test_rejects_empty_detail(self) -> None:
        with pytest.raises(ValueError, match="detail"):
            _result(detail="")

    def test_rejects_whitespace_only_detail(self) -> None:
        with pytest.raises(ValueError, match="detail"):
            _result(detail="   ")

    def test_round_trips_through_dict(self) -> None:
        result = _result(healthy=False, detail="unreachable")
        assert HealthCheckResult.from_dict(result.to_dict()) == result

    def test_is_frozen(self) -> None:
        result = _result()
        with pytest.raises(AttributeError):
            result.healthy = False  # type: ignore[misc]


class TestClassifyStatus:
    def test_rejects_empty_checks(self) -> None:
        with pytest.raises(ValueError, match="checks"):
            classify_status(())

    def test_all_healthy_is_healthy(self) -> None:
        assert classify_status((_result(), _result())) is HealthStatus.HEALTHY

    def test_all_unhealthy_is_unhealthy(self) -> None:
        checks = (_result(healthy=False), _result(healthy=False))
        assert classify_status(checks) is HealthStatus.UNHEALTHY

    def test_mixed_is_degraded(self) -> None:
        checks = (_result(healthy=True), _result(healthy=False))
        assert classify_status(checks) is HealthStatus.DEGRADED


class TestPlatformHealth:
    def test_valid_health_constructs(self) -> None:
        health = _health()
        assert health.status is HealthStatus.HEALTHY

    def test_rejects_naive_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _health(timestamp=datetime(2024, 1, 1))

    def test_rejects_empty_checks(self) -> None:
        with pytest.raises(ValueError, match="checks"):
            PlatformHealth(
                status=HealthStatus.HEALTHY,
                checks=(),
                timestamp=T0,
                version="0.12.0",
                git_commit="abc1234",
            )

    def test_rejects_empty_version(self) -> None:
        with pytest.raises(ValueError, match="version"):
            _health(version="")

    def test_rejects_empty_git_commit(self) -> None:
        with pytest.raises(ValueError, match="git_commit"):
            _health(git_commit="")

    def test_rejects_status_inconsistent_with_checks(self) -> None:
        with pytest.raises(ValueError, match="status"):
            _health(status=HealthStatus.UNHEALTHY, checks=(_result(),))

    def test_accepts_consistent_degraded_status(self) -> None:
        checks = (_result(healthy=True), _result(healthy=False))
        health = _health(status=HealthStatus.DEGRADED, checks=checks)
        assert health.status is HealthStatus.DEGRADED

    def test_round_trips_through_dict(self) -> None:
        health = _health(checks=(_result(), _result(name="market_data")))
        assert PlatformHealth.from_dict(health.to_dict()) == health

    def test_is_frozen(self) -> None:
        health = _health()
        with pytest.raises(AttributeError):
            health.version = "0.13.0"  # type: ignore[misc]


class TestPlatformInfo:
    def test_valid_info_constructs(self) -> None:
        info = _info()
        assert info.version == "0.12.0"

    def test_rejects_naive_build_time(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _info(build_time=datetime(2024, 1, 1))

    def test_rejects_empty_version(self) -> None:
        with pytest.raises(ValueError, match="version"):
            _info(version="")

    def test_rejects_empty_git_commit(self) -> None:
        with pytest.raises(ValueError, match="git_commit"):
            _info(git_commit="")

    def test_rejects_empty_python_version(self) -> None:
        with pytest.raises(ValueError, match="python_version"):
            _info(python_version="")

    def test_round_trips_through_dict(self) -> None:
        info = _info()
        assert PlatformInfo.from_dict(info.to_dict()) == info

    def test_is_frozen(self) -> None:
        info = _info()
        with pytest.raises(AttributeError):
            info.version = "0.13.0"  # type: ignore[misc]


class TestRuntimeContext:
    def test_valid_context_constructs(self) -> None:
        context = _context()
        assert context.environment == "production"

    def test_rejects_naive_startup_time(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _context(startup_time=datetime(2024, 1, 1))

    def test_rejects_empty_environment(self) -> None:
        with pytest.raises(ValueError, match="environment"):
            _context(environment="")

    def test_round_trips_through_dict(self) -> None:
        context = _context()
        assert RuntimeContext.from_dict(context.to_dict()) == context

    def test_is_frozen(self) -> None:
        context = _context()
        with pytest.raises(AttributeError):
            context.environment = "test"  # type: ignore[misc]


class TestDeploymentInfo:
    def test_valid_deployment_constructs(self) -> None:
        deployment = _deployment()
        assert deployment.deployment_id == "deploy-001"
        assert deployment.rollback_target is None

    def test_rejects_naive_build_time(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _deployment(build_time=datetime(2024, 1, 1))

    def test_rejects_empty_version(self) -> None:
        with pytest.raises(ValueError, match="version"):
            _deployment(version="")

    def test_rejects_empty_git_commit(self) -> None:
        with pytest.raises(ValueError, match="git_commit"):
            _deployment(git_commit="")

    def test_rejects_empty_deployment_environment(self) -> None:
        with pytest.raises(ValueError, match="deployment_environment"):
            _deployment(deployment_environment="")

    def test_rejects_empty_deployment_id(self) -> None:
        with pytest.raises(ValueError, match="deployment_id"):
            _deployment(deployment_id="")

    def test_rejects_empty_string_rollback_target(self) -> None:
        with pytest.raises(ValueError, match="rollback_target"):
            _deployment(rollback_target="")

    def test_allows_none_rollback_target(self) -> None:
        deployment = _deployment(rollback_target=None)
        assert deployment.rollback_target is None

    def test_allows_set_rollback_target(self) -> None:
        deployment = _deployment(rollback_target="deploy-000")
        assert deployment.rollback_target == "deploy-000"

    def test_round_trips_through_dict(self) -> None:
        deployment = _deployment(rollback_target="deploy-000")
        assert DeploymentInfo.from_dict(deployment.to_dict()) == deployment

    def test_round_trips_through_dict_without_rollback_target(self) -> None:
        deployment = _deployment()
        assert DeploymentInfo.from_dict(deployment.to_dict()) == deployment

    def test_is_frozen(self) -> None:
        deployment = _deployment()
        with pytest.raises(AttributeError):
            deployment.deployment_id = "other"  # type: ignore[misc]


class TestDiagnosticReport:
    def test_valid_report_constructs_without_deployment(self) -> None:
        report = _diagnostic()
        assert report.deployment_info is None

    def test_valid_report_constructs_with_deployment(self) -> None:
        report = _diagnostic(deployment_info=_deployment())
        assert report.deployment_info is not None
        assert report.deployment_info.deployment_id == "deploy-001"

    def test_rejects_naive_generated_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _diagnostic(generated_at=datetime(2024, 1, 1))

    def test_round_trips_through_dict_without_deployment(self) -> None:
        report = _diagnostic()
        assert DiagnosticReport.from_dict(report.to_dict()) == report

    def test_round_trips_through_dict_with_deployment(self) -> None:
        report = _diagnostic(deployment_info=_deployment())
        assert DiagnosticReport.from_dict(report.to_dict()) == report

    def test_is_frozen(self) -> None:
        report = _diagnostic()
        with pytest.raises(AttributeError):
            report.generated_at = T0  # type: ignore[misc]
