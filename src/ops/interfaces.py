"""`HealthCheck` -- the single interface every subsystem probe in
`ops.checks` implements. `ops.health.evaluate_health` depends only on
this Protocol, never on a concrete check implementation, so new
subsystem checks can be added without touching the aggregation logic.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ops.models import HealthCheckResult


@runtime_checkable
class HealthCheck(Protocol):
    """A single subsystem probe. `name` identifies the subsystem in a
    `PlatformHealth` report; `check()` runs the probe and always returns
    a `HealthCheckResult` -- it must not raise for an expected failure
    (an unreachable provider, a missing model file), only for a genuine
    programming error."""

    @property
    def name(self) -> str: ...

    def check(self) -> HealthCheckResult: ...


__all__ = ["HealthCheck"]
