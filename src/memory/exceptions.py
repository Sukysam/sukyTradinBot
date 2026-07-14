"""Exception hierarchy for the Adaptive Learning / Memory Loop.

All derive from `MemoryLoopError` (itself an `AppError`), matching the
same "catch specific exceptions, fail loudly, never swallow silently"
pattern every other package in this platform follows. Named
`MemoryLoopError`, not `MemoryError`, to avoid shadowing the Python
builtin of the same name -- every other package in this handbook follows
the plain `<Package>Error` convention (`BacktestError`, `RiskError`,
`HMMError`), but `memory` collides with a real builtin, so this is a
deliberate, documented exception to that naming pattern.
"""

from __future__ import annotations

from common.errors import AppError


class MemoryLoopError(AppError):
    """Base class for all errors raised by `memory`."""


class CorruptExperienceLogError(MemoryLoopError):
    """Raised when a persisted experience log contains a line that
    doesn't deserialize into a valid `ExperienceRecord` -- never silently
    skipped, since a corrupt line usually means the single-writer
    assumption (see `store.JsonlExperienceStore`) was violated."""


__all__ = ["CorruptExperienceLogError", "MemoryLoopError"]
