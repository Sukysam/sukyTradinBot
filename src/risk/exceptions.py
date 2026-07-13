"""Exception hierarchy for the Risk Manager.

All derive from `RiskError` (itself an `AppError`), matching the same
"catch specific exceptions, fail loudly, never swallow silently" pattern
every other package in this platform follows.
"""

from __future__ import annotations

from common.errors import AppError


class RiskError(AppError):
    """Base class for all errors raised by `risk`."""


class InvalidSizingResultError(RiskError):
    """Raised when a `SizingRule` returns an allocation larger than the one
    it was given -- sizing is a reduce-only stage by contract (see
    ADR-010's `approved_allocation` bound), so a rule that increases
    allocation is a bug in that rule, not a legitimate outcome to accept
    silently. Defense in depth alongside `ExecutionDecision`'s own
    construction-time bound.
    """


__all__ = [
    "InvalidSizingResultError",
    "RiskError",
]
