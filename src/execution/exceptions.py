"""Exception hierarchy for the Execution Layer.

All derive from `ExecutionError` (itself an `AppError`), matching the
same "catch specific exceptions, fail loudly, never swallow silently"
pattern every other package in this platform follows.
"""

from __future__ import annotations

from common.errors import AppError


class ExecutionError(AppError):
    """Base class for all errors raised by `execution`."""


class TransientBrokerError(ExecutionError):
    """Raised internally by `execution.retry.submit_with_retry` when a
    `BrokerAdapter.submit_order` call returns `submitted=False` -- bridges
    that result-based failure into `common.retry.call_with_retry`'s
    exception-based retry mechanism. Never raised by a `BrokerAdapter`
    itself, and never expected to escape `submit_with_retry`.
    """


__all__ = ["ExecutionError", "TransientBrokerError"]
