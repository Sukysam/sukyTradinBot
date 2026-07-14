"""Minimal, zero-dependency tracing hooks.

`Span` records one named unit of work's start/end time and duration;
`Tracer.span()` is a context manager that times its block and hands the
completed `Span` to every registered hook. No distributed-tracing SDK
integration (OpenTelemetry, Jaeger, etc.) -- a real backend integration
is future work once one is actually chosen, not assumed here; see
ADR-023's Alternatives Considered. `Tracer` only produces `Span`s and
calls hooks with them -- what a hook does with a `Span` (log it, export
it, discard it) is entirely up to the caller that registered it, the
same dependency-injection convention `ops.checks`' probes and
`ops.health.evaluate_health`'s `clock` parameter already follow.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime

from common.interfaces import Clock
from common.time import SystemClock, require_utc

_DEFAULT_CLOCK: Clock = SystemClock()


@dataclass(frozen=True)
class Span:
    """One completed unit of traced work."""

    name: str
    started_at: datetime
    ended_at: datetime
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_utc(self.started_at, "started_at")
        require_utc(self.ended_at, "ended_at")
        if not self.name:
            raise ValueError("name must not be empty")
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must not precede started_at")

    @property
    def duration_seconds(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()


class Tracer:
    """Produces `Span`s and notifies registered hooks when one
    completes. Hooks are called in registration order; a hook that
    raises propagates immediately -- the same "fail loudly, never
    swallow silently" convention every module in this codebase follows,
    rather than a tracer that could silently drop a hook's error."""

    def __init__(
        self,
        *,
        clock: Clock = _DEFAULT_CLOCK,
        hooks: tuple[Callable[[Span], None], ...] = (),
    ) -> None:
        self._clock = clock
        self._hooks: list[Callable[[Span], None]] = list(hooks)

    def add_hook(self, hook: Callable[[Span], None]) -> None:
        self._hooks.append(hook)

    @contextmanager
    def span(self, name: str, **metadata: str) -> Iterator[None]:
        started_at = self._clock.now()
        try:
            yield
        finally:
            ended_at = self._clock.now()
            completed = Span(name=name, started_at=started_at, ended_at=ended_at, metadata=metadata)
            for hook in self._hooks:
                hook(completed)


__all__ = ["Span", "Tracer"]
