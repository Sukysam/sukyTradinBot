"""Base interfaces shared across this repository's future components.

Every `Protocol` here is domain-neutral by design — nothing about trading,
regimes, brokers, or strategies. They exist because more than one future
component will need the same shape of dependency (an injectable time
source, a start/stop lifecycle, a liveness check), and defining that shape
once, ahead of any concrete implementation, is what lets those components
be built independently and tested against a fake — see
docs/engineering-handbook/Standards/Python Style Guide.md's guidance on
`typing.Protocol`: reach for it when a dependency has more than one
implementation, or doesn't exist yet and needs a stable contract to build
against.

Do not add a domain-specific interface here (e.g. anything trading-,
broker-, or model-shaped) — this module is foundation-only. Per
docs/engineering-handbook/01_SYSTEM_ARCHITECT.md's coding standards,
`Protocol` classes normally live at the top of the module that consumes
them, not in a shared interfaces module; the ones below are the deliberate
exception, because "the consumer" at this stage is every future module
equally, not any one of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Supplies the current time. See `common.time` for implementations.

    Inject this into anything whose behavior depends on "now" instead of
    calling `datetime.now()` internally, so that behavior can be tested
    deterministically with `common.time.FixedClock`.
    """

    def now(self) -> datetime:
        """Return the current time as a timezone-aware `datetime`."""
        ...


class HealthStatus(str, Enum):
    """Closed set of outcomes a health check can report."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class HealthCheckResult:
    """The result of one `HealthCheck.check()` call."""

    status: HealthStatus
    detail: str = ""


@runtime_checkable
class HealthCheck(Protocol):
    """Reports whether a component is fit to serve traffic/do work.

    Intended for anything with an external dependency worth verifying at
    startup or on a monitoring interval (a database connection, a model
    file, a broker session) — the check itself does not repair anything,
    it only reports, matching this repository's "the risk/health layer
    answers a question and returns a decision; it doesn't act on it"
    pattern already established by `risk_manager.evaluate_trade`.
    """

    def check(self) -> HealthCheckResult:
        """Run the check now and report the result. Must not raise for an
        unhealthy dependency — an exception here should mean the health
        check itself is broken, not that the thing it's checking is down.
        """
        ...


@runtime_checkable
class Service(Protocol):
    """A component with an explicit async start/stop lifecycle.

    Modeled on the lifecycle every long-lived pipeline in this system
    already needs (see `regime-trader/main.py`'s three concurrent
    pipelines): a `Service` starts, runs until asked to stop, and stops
    cleanly. This `Protocol` formalizes that shape so future long-lived
    components can be supervised uniformly, without prescribing anything
    about what any particular service does while running.
    """

    async def start(self) -> None:
        """Begin running. Must return once startup work is complete; a
        `Service` that runs indefinitely does so on its own task, not by
        blocking inside `start()`.
        """
        ...

    async def stop(self) -> None:
        """Stop cleanly. Must be safe to call even if `start()` was never
        called, and idempotent — calling it twice must not raise.
        """
        ...


__all__ = [
    "Clock",
    "HealthCheck",
    "HealthCheckResult",
    "HealthStatus",
    "Service",
]
