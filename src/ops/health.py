"""`evaluate_health` -- the single aggregation entrypoint turning a
sequence of `HealthCheck`s into a `PlatformHealth` report -- and
`require_healthy`, the fail-fast startup gate built on top of it.
"""

from __future__ import annotations

from collections.abc import Sequence

from common.interfaces import Clock
from common.time import SystemClock
from ops.exceptions import UnhealthyPlatformError
from ops.interfaces import HealthCheck
from ops.models import HealthStatus, PlatformHealth, classify_status

_DEFAULT_CLOCK: Clock = SystemClock()


def evaluate_health(
    checks: Sequence[HealthCheck],
    *,
    version: str,
    git_commit: str,
    clock: Clock = _DEFAULT_CLOCK,
) -> PlatformHealth:
    """Run every `HealthCheck` in `checks` and aggregate the results into
    one `PlatformHealth` report. `status` is derived from the individual
    results via `classify_status`, so it can never disagree with them."""
    results = tuple(check.check() for check in checks)
    return PlatformHealth(
        status=classify_status(results),
        checks=results,
        timestamp=clock.now(),
        version=version,
        git_commit=git_commit,
    )


def require_healthy(health: PlatformHealth) -> None:
    """Raise `UnhealthyPlatformError` unless `health.status` is
    `HealthStatus.HEALTHY`. Intended as a fail-fast gate at process
    startup: a `DEGRADED` or `UNHEALTHY` report must stop the process
    from starting, not be logged and ignored."""
    if health.status is not HealthStatus.HEALTHY:
        failing = ", ".join(check.name for check in health.checks if not check.healthy)
        raise UnhealthyPlatformError(
            f"platform health is {health.status.value}; failing checks: {failing}"
        )


__all__ = ["evaluate_health", "require_healthy"]
