"""Retry with exponential backoff for transient failures.

Generic infrastructure for any future call to an unreliable external
dependency (a broker API, a model download, a network request) — this
module contains no knowledge of what it might eventually retry. Per
docs/engineering-handbook/03_BACKEND_ENGINEER.md, "retry/backoff logic for
transient API errors belongs at the client layer, not scattered into call
sites — one policy, one place"; this is that one place.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

from common.errors import RetryExhaustedError

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_INITIAL_DELAY_SECONDS = 0.5
DEFAULT_BACKOFF_MULTIPLIER = 2.0


@dataclass(frozen=True)
class RetryPolicy:
    """Explicit, named retry configuration — never magic numbers at a call
    site. See docs/engineering-handbook/Standards/Python Style Guide.md's
    "Constants" section.
    """

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    initial_delay_seconds: float = DEFAULT_INITIAL_DELAY_SECONDS
    backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER
    exceptions: tuple[type[Exception], ...] = (Exception,)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.initial_delay_seconds < 0:
            raise ValueError(
                f"initial_delay_seconds must be >= 0, got {self.initial_delay_seconds}"
            )
        if self.backoff_multiplier < 1:
            raise ValueError(f"backoff_multiplier must be >= 1, got {self.backoff_multiplier}")

    def delay_for_attempt(self, attempt: int) -> float:
        """Delay (seconds) before retrying, where `attempt` is 1-indexed:
        the delay before the 2nd attempt is `initial_delay_seconds`, before
        the 3rd is `initial_delay_seconds * backoff_multiplier`, etc.
        """
        if attempt < 1:
            raise ValueError(f"attempt must be >= 1, got {attempt}")
        return self.initial_delay_seconds * (self.backoff_multiplier ** (attempt - 1))


def call_with_retry(
    func: Callable[[], T],
    policy: RetryPolicy | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call `func` (a zero-argument callable), retrying on failure per
    `policy`. Raises `RetryExhaustedError`, chained from the last
    underlying exception, once `policy.max_attempts` is reached.

    `sleep` is injectable so tests can verify retry/backoff behavior
    without actually waiting — pass a no-op or recording stand-in.
    Wrap the target call in a `lambda` or `functools.partial` to pass
    arguments, keeping this function's own signature simple.
    """
    policy = policy or RetryPolicy()
    last_exc: Exception | None = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return func()
        except policy.exceptions as exc:
            last_exc = exc
            logger.warning(
                "Attempt %d/%d failed: %s", attempt, policy.max_attempts, exc, exc_info=False
            )
            if attempt < policy.max_attempts:
                sleep(policy.delay_for_attempt(attempt))

    assert last_exc is not None  # loop always runs >= 1 time; mypy narrowing aid
    raise RetryExhaustedError(
        f"All {policy.max_attempts} attempts failed; last error: {last_exc}"
    ) from last_exc


__all__ = ["RetryPolicy", "call_with_retry"]
