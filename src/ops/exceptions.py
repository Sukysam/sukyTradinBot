"""Exception hierarchy for operational tooling.

All derive from `OpsError` (itself an `AppError`), matching the same
"catch specific exceptions, fail loudly, never swallow silently" pattern
every other package in this platform follows.
"""

from __future__ import annotations

from common.errors import AppError


class OpsError(AppError):
    """Base class for all errors raised by `ops`."""


class UnhealthyPlatformError(OpsError):
    """Raised by `ops.health.require_healthy` when a `PlatformHealth`
    report is not `HealthStatus.HEALTHY` -- the fail-fast startup gate.
    Never caught and silently ignored by production start-up code; a
    process that starts anyway despite a failing dependency check is
    exactly the "silently no-op" failure mode
    [00_MASTER_CHARTER.md](../../docs/engineering-handbook/00_MASTER_CHARTER.md)
    invariant #4 exists to prevent."""


__all__ = ["OpsError", "UnhealthyPlatformError"]
