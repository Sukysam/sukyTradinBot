"""Exception hierarchy for the Strategy Engine.

All derive from `StrategyError` (itself an `AppError`), matching the same
"catch specific exceptions, fail loudly, never swallow silently" pattern
every other package in this platform follows.
"""

from __future__ import annotations

from common.errors import AppError


class StrategyError(AppError):
    """Base class for all errors raised by `strategy`."""


class StrategyNotFoundError(StrategyError):
    """Raised when `StrategyRegistry.get` is asked for a `strategy_id`
    that was never registered.
    """


class UnsupportedRegimeError(StrategyError):
    """Raised when no registered strategy declares support for a given
    `regime_id`, and no `default_strategy_id` fallback is configured --
    never silently falls back to an arbitrary strategy.
    """


class AmbiguousStrategyError(StrategyError):
    """Raised when more than one registered strategy declares support for
    the same `regime_id` -- a registration/configuration error, since
    dispatch must be deterministic (see `Standards/StrategyDecision
    Contract.md`'s "deterministic regime-to-strategy mapping" requirement).
    """


class ContractViolationError(StrategyError):
    """Raised when a `FeatureVector`/`RegimeState` pair handed to
    `StrategyService.decide` are internally inconsistent (different
    `symbol` or `timestamp`) -- never silently produces a decision from
    mismatched inputs.
    """


__all__ = [
    "AmbiguousStrategyError",
    "ContractViolationError",
    "StrategyError",
    "StrategyNotFoundError",
    "UnsupportedRegimeError",
]
