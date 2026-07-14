"""Exception hierarchy for the NLP & Event Processing layer.

All derive from `NlpError` (itself an `AppError`), matching the same
"catch specific exceptions, fail loudly, never swallow silently" pattern
every other package in this platform follows.
"""

from __future__ import annotations

from common.errors import AppError


class NlpError(AppError):
    """Base class for all errors raised by `nlp`."""


class CorruptNewsLogError(NlpError):
    """Raised when a persisted news log contains a line that doesn't
    deserialize into a valid `NewsItem` -- never silently skipped, since
    a corrupt line usually means the single-writer assumption (see
    `store.JsonlNewsItemStore`) was violated."""


__all__ = ["CorruptNewsLogError", "NlpError"]
