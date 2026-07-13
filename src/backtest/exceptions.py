"""Exception hierarchy for the Backtesting & Validation layer.

All derive from `BacktestError` (itself an `AppError`), matching the
same "catch specific exceptions, fail loudly, never swallow silently"
pattern every other package in this platform follows.
"""

from __future__ import annotations

from common.errors import AppError


class BacktestError(AppError):
    """Base class for all errors raised by `backtest`."""


class InsufficientReplayHistoryError(BacktestError):
    """Raised when there aren't enough bars before `start_date` to fill
    the feature/regime lookback window a replay step needs -- never
    silently starts the replay from a shorter, unstated window."""


__all__ = ["BacktestError", "InsufficientReplayHistoryError"]
