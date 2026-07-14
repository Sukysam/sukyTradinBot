"""Concrete `HealthCheck` implementations.

One generic `CallableHealthCheck` wraps any zero-argument probe -- the
same "dependency injected, never constructed internally" convention
`BacktestEngine.run` and every other orchestration point in this codebase
follows: a check never opens a real broker connection, database handle,
or model file itself, it only calls the probe it was given. Ten small,
named factory functions build one `CallableHealthCheck` per subsystem
the platform depends on, so each is individually discoverable and
testable without exercising the others.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from common.interfaces import Clock
from common.time import SystemClock
from ops.models import HealthCheckResult

_DEFAULT_CLOCK: Clock = SystemClock()


@dataclass(frozen=True)
class CallableHealthCheck:
    """A `HealthCheck` backed by a zero-argument `probe`.

    `probe` returns `True`/`False`, or raises -- either way `check()`
    converts the outcome into a `HealthCheckResult` and never lets the
    probe's exception propagate, since one subsystem being unreachable
    must not prevent the other nine from being reported."""

    _name: str
    probe: Callable[[], bool]
    clock: Clock = field(default_factory=SystemClock)

    @property
    def name(self) -> str:
        return self._name

    def check(self) -> HealthCheckResult:
        try:
            healthy = self.probe()
        except Exception as exc:
            return HealthCheckResult(
                name=self._name,
                healthy=False,
                detail=f"probe raised {type(exc).__name__}: {exc}",
                checked_at=self.clock.now(),
            )
        detail = "ok" if healthy else "probe returned False"
        return HealthCheckResult(
            name=self._name,
            healthy=healthy,
            detail=detail,
            checked_at=self.clock.now(),
        )


def configuration_check(
    probe: Callable[[], bool], *, clock: Clock = _DEFAULT_CLOCK
) -> CallableHealthCheck:
    """Configuration loaded."""
    return CallableHealthCheck("configuration", probe, clock)


def market_data_check(
    probe: Callable[[], bool], *, clock: Clock = _DEFAULT_CLOCK
) -> CallableHealthCheck:
    """Market data providers reachable."""
    return CallableHealthCheck("market_data", probe, clock)


def model_artifact_check(
    probe: Callable[[], bool], *, clock: Clock = _DEFAULT_CLOCK
) -> CallableHealthCheck:
    """Model artifacts available."""
    return CallableHealthCheck("model_artifact", probe, clock)


def feature_registry_check(
    probe: Callable[[], bool], *, clock: Clock = _DEFAULT_CLOCK
) -> CallableHealthCheck:
    """Feature registry loaded."""
    return CallableHealthCheck("feature_registry", probe, clock)


def hmm_model_check(
    probe: Callable[[], bool], *, clock: Clock = _DEFAULT_CLOCK
) -> CallableHealthCheck:
    """HMM model available."""
    return CallableHealthCheck("hmm_model", probe, clock)


def strategy_registry_check(
    probe: Callable[[], bool], *, clock: Clock = _DEFAULT_CLOCK
) -> CallableHealthCheck:
    """Strategy registry initialized."""
    return CallableHealthCheck("strategy_registry", probe, clock)


def risk_service_check(
    probe: Callable[[], bool], *, clock: Clock = _DEFAULT_CLOCK
) -> CallableHealthCheck:
    """Risk service initialized."""
    return CallableHealthCheck("risk_service", probe, clock)


def execution_adapter_check(
    probe: Callable[[], bool], *, clock: Clock = _DEFAULT_CLOCK
) -> CallableHealthCheck:
    """Execution adapter configured."""
    return CallableHealthCheck("execution_adapter", probe, clock)


def memory_store_check(
    probe: Callable[[], bool], *, clock: Clock = _DEFAULT_CLOCK
) -> CallableHealthCheck:
    """Memory store accessible."""
    return CallableHealthCheck("memory_store", probe, clock)


def nlp_pipeline_check(
    probe: Callable[[], bool], *, clock: Clock = _DEFAULT_CLOCK
) -> CallableHealthCheck:
    """NLP pipeline ready."""
    return CallableHealthCheck("nlp_pipeline", probe, clock)


__all__ = [
    "CallableHealthCheck",
    "configuration_check",
    "execution_adapter_check",
    "feature_registry_check",
    "hmm_model_check",
    "market_data_check",
    "memory_store_check",
    "model_artifact_check",
    "nlp_pipeline_check",
    "risk_service_check",
    "strategy_registry_check",
]
