from __future__ import annotations

from datetime import datetime, timezone

from common.interfaces import Clock, HealthCheck, HealthCheckResult, HealthStatus, Service
from common.time import FixedClock, SystemClock


def test_system_clock_satisfies_clock_protocol() -> None:
    assert isinstance(SystemClock(), Clock)


def test_fixed_clock_satisfies_clock_protocol() -> None:
    assert isinstance(FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc)), Clock)


def test_health_check_result_is_frozen_value_object() -> None:
    result = HealthCheckResult(status=HealthStatus.HEALTHY, detail="all good")
    assert result.status == HealthStatus.HEALTHY
    assert result.detail == "all good"


class _AlwaysHealthy:
    def check(self) -> HealthCheckResult:
        return HealthCheckResult(status=HealthStatus.HEALTHY)


def test_concrete_class_satisfies_health_check_protocol() -> None:
    assert isinstance(_AlwaysHealthy(), HealthCheck)
    assert _AlwaysHealthy().check().status == HealthStatus.HEALTHY


class _NoOpService:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


def test_concrete_class_satisfies_service_protocol() -> None:
    assert isinstance(_NoOpService(), Service)


async def test_service_lifecycle_methods_are_awaitable() -> None:
    service = _NoOpService()
    await service.start()
    assert service.started is True
    await service.stop()
    assert service.stopped is True
