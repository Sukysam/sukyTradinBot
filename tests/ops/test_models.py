"""Tests for `ops.models`: `HealthCheckResult` and `PlatformHealth`'s
construction-time invariants, serialization, and `classify_status`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ops.models import HealthCheckResult, HealthStatus, PlatformHealth, classify_status

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
