"""Exception hierarchy for the Signal Orchestration layer.

All derive from `OrchestrationError` (itself an `AppError`), matching the
same "catch specific exceptions, fail loudly, never swallow silently"
pattern every other package in this platform follows.
"""

from __future__ import annotations

from common.errors import AppError


class OrchestrationError(AppError):
    """Base class for all errors raised by `orchestration`."""


class MismatchedSignalError(OrchestrationError):
    """Raised when an advisory `LearningDecision`/`NewsSignal` passed to
    `arbitrate` doesn't share the primary `StrategyDecision`'s
    `symbol`/`strategy_id`/`regime_id` context -- never silently
    arbitrated against the wrong signal."""


__all__ = ["MismatchedSignalError", "OrchestrationError"]
