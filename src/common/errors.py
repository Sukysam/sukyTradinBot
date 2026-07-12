"""Base exception hierarchy for the foundation package.

Every exception raised by `common` derives from `AppError` so calling code
can catch "something in our own infrastructure went wrong" without also
swallowing unrelated third-party or stdlib exceptions. Domain packages
(trading, backtesting, etc.) are expected to define their own subclasses
of `AppError` rather than raising it directly, the same way this module
never raises a bare `Exception` — see
docs/engineering-handbook/Standards/Coding Standards.md's "Error handling"
section: catch specific exceptions, fail loudly, never swallow silently.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all errors raised by first-party code in this repo."""


class ConfigurationError(AppError):
    """Raised when application configuration is missing or invalid.

    Distinct from a plain `ValueError` so callers can distinguish "you
    passed this function a bad argument" from "the environment this
    process is running in is misconfigured" — the latter is an
    operational condition someone deploying the service needs to see and
    fix, not a programming bug.
    """


class RetryExhaustedError(AppError):
    """Raised by `common.retry` once all attempts have been exhausted.

    Chains the last underlying exception via `raise ... from last_exc` at
    the call site so the original failure is never lost.
    """
