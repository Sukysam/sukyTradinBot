"""Exception hierarchy for the runtime package.

Derives from `common.errors.AppError`, matching every other package's
"catch specific exceptions, fail loudly, never swallow silently"
convention.
"""

from __future__ import annotations

from common.errors import AppError


class RuntimeAppError(AppError):
    """Base class for all errors raised by `app`."""


class GitCommitUnavailableError(RuntimeAppError):
    """Raised when the running git commit can't be determined -- a
    `RuntimeContext`/`PlatformHealth` built with a fabricated commit
    hash is worse than one that fails loudly, matching
    `backtest.engine.current_git_commit`'s identical reasoning."""


__all__ = ["GitCommitUnavailableError", "RuntimeAppError"]
