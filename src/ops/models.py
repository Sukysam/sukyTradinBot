"""`PlatformHealth` and `HealthCheckResult` -- the operational model
`ops.health.evaluate_health` produces. Not a domain contract like
`FinalDecision` (Milestone 12 is operational maturity work, not a new
decision-pipeline stage -- per direct product-owner review, forcing it
into the freeze-first domain-contract cadence would be an artificial
abstraction), but still a small, stable interface worth documenting: the
one shape every health endpoint, dashboard, and deployment automation
script in this platform is meant to read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from common.time import require_utc


class HealthStatus(str, Enum):
    """Aggregate classification of a `PlatformHealth` report, mirroring
    `orchestration.models.ArbitrationOutcome`'s role: downstream code
    branches on `health.status is HealthStatus.UNHEALTHY` rather than
    reconstructing that classification from individual check results.
    Cross-checked against `checks` at construction -- see
    `PlatformHealth.__post_init__` and `classify_status`.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class HealthCheckResult:
    """One `ops.interfaces.HealthCheck`'s outcome. `detail` is never
    empty, the same "never produce an unexplained result" principle
    every decision-shaped contract in this handbook already carries --
    a health check that can't say *why* it passed or failed isn't
    useful for on-call debugging."""

    name: str
    healthy: bool
    detail: str
    checked_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.checked_at, "checked_at")
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.detail.strip():
            raise ValueError("detail must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "detail": self.detail,
            "checked_at": self.checked_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HealthCheckResult:
        return cls(
            name=data["name"],
            healthy=data["healthy"],
            detail=data["detail"],
            checked_at=datetime.fromisoformat(data["checked_at"]),
        )


def classify_status(checks: Sequence[HealthCheckResult]) -> HealthStatus:
    """`HEALTHY` iff every check passed, `UNHEALTHY` iff every check
    failed, `DEGRADED` otherwise. Shared by `PlatformHealth`'s own
    construction-time validation and `ops.health.evaluate_health`, the
    same single-source-of-truth pattern `orchestration.signals.
    classify_outcome` already established, so the two can never
    silently compute a different answer."""
    if not checks:
        raise ValueError("checks must not be empty")
    healthy_count = sum(1 for check in checks if check.healthy)
    if healthy_count == len(checks):
        return HealthStatus.HEALTHY
    if healthy_count == 0:
        return HealthStatus.UNHEALTHY
    return HealthStatus.DEGRADED


@dataclass(frozen=True)
class PlatformHealth:
    """An aggregated health report -- one `HealthCheckResult` per
    subsystem, plus enough metadata (`version`, `git_commit`) to
    correlate a report against the exact deployed build it came from."""

    status: HealthStatus
    checks: tuple[HealthCheckResult, ...]
    timestamp: datetime
    version: str
    git_commit: str

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not self.checks:
            raise ValueError("checks must not be empty")
        if not self.version:
            raise ValueError("version must not be empty")
        if not self.git_commit:
            raise ValueError("git_commit must not be empty")
        expected = classify_status(self.checks)
        if self.status is not expected:
            raise ValueError(
                f"status {self.status!r} is inconsistent with checks " f"(expected {expected!r})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "checks": [check.to_dict() for check in self.checks],
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "git_commit": self.git_commit,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PlatformHealth:
        return cls(
            status=HealthStatus(data["status"]),
            checks=tuple(HealthCheckResult.from_dict(item) for item in data["checks"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            version=data["version"],
            git_commit=data["git_commit"],
        )


@dataclass(frozen=True)
class PlatformInfo:
    """Static build identity -- version, commit, when it was built, and
    which Python it was built for. Deliberately separate from
    `PlatformHealth`: `PlatformHealth` changes on every evaluation
    (a check can flip from healthy to unhealthy between two calls),
    `PlatformInfo` does not change for the lifetime of a running
    process. Pairs naturally with `PlatformHealth` wherever an
    operational endpoint, exported metric, or structured log line needs
    to say *which build* produced a report, without exposing anything
    about how that build works internally."""

    version: str
    git_commit: str
    build_time: datetime
    python_version: str

    def __post_init__(self) -> None:
        require_utc(self.build_time, "build_time")
        if not self.version:
            raise ValueError("version must not be empty")
        if not self.git_commit:
            raise ValueError("git_commit must not be empty")
        if not self.python_version:
            raise ValueError("python_version must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "git_commit": self.git_commit,
            "build_time": self.build_time.isoformat(),
            "python_version": self.python_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PlatformInfo:
        return cls(
            version=data["version"],
            git_commit=data["git_commit"],
            build_time=datetime.fromisoformat(data["build_time"]),
            python_version=data["python_version"],
        )


@dataclass(frozen=True)
class RuntimeContext:
    """The one immutable object every operational surface -- health
    checks, metrics, logging, alerts, deployment tooling -- can read to
    answer "what build, in what environment, has been running since
    when." `ops.startup.build_runtime_context` is the only place that
    constructs one, and it will not return one unless configuration
    loaded and every required secret resolved -- constructing a
    `RuntimeContext` *is* the proof that startup validation succeeded,
    rather than that proof being a separate field to go stale.

    Deliberately excludes two things a first reading of "runtime
    context" might expect: it carries no secret material (proving
    secrets resolved is `ops.validation`'s job; storing the resolved
    values on an object that gets passed around and possibly logged is
    a needless leak surface), and it does not duplicate `git_commit`
    from `platform_info` (`RuntimeContext.platform_info.git_commit` is
    the one place that lives).

    Distinct from `PlatformHealth`: this describes *identity*,
    established once at startup and immutable for the process's life;
    `PlatformHealth` describes *current state*, re-evaluated on demand
    and free to change between any two calls.
    """

    platform_info: PlatformInfo
    environment: str
    startup_time: datetime

    def __post_init__(self) -> None:
        require_utc(self.startup_time, "startup_time")
        if not self.environment:
            raise ValueError("environment must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform_info": self.platform_info.to_dict(),
            "environment": self.environment,
            "startup_time": self.startup_time.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RuntimeContext:
        return cls(
            platform_info=PlatformInfo.from_dict(data["platform_info"]),
            environment=data["environment"],
            startup_time=datetime.fromisoformat(data["startup_time"]),
        )


@dataclass(frozen=True)
class DeploymentInfo:
    """One particular deployment instance -- distinct from
    `PlatformInfo`, which describes the *build*: the same build
    (`version`/`git_commit`) can be deployed more than once, to more
    than one `deployment_environment`, each a different
    `DeploymentInfo` with its own `deployment_id`. `rollback_target`,
    when set, names the `deployment_id` this deployment would roll back
    to if it needed to -- `None` means no rollback target has been
    designated (e.g. this is the first deployment to this
    environment)."""

    version: str
    git_commit: str
    build_time: datetime
    deployment_environment: str
    deployment_id: str
    rollback_target: str | None = None

    def __post_init__(self) -> None:
        require_utc(self.build_time, "build_time")
        if not self.version:
            raise ValueError("version must not be empty")
        if not self.git_commit:
            raise ValueError("git_commit must not be empty")
        if not self.deployment_environment:
            raise ValueError("deployment_environment must not be empty")
        if not self.deployment_id:
            raise ValueError("deployment_id must not be empty")
        if self.rollback_target is not None and not self.rollback_target:
            raise ValueError("rollback_target must not be an empty string; use None instead")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "git_commit": self.git_commit,
            "build_time": self.build_time.isoformat(),
            "deployment_environment": self.deployment_environment,
            "deployment_id": self.deployment_id,
            "rollback_target": self.rollback_target,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DeploymentInfo:
        return cls(
            version=data["version"],
            git_commit=data["git_commit"],
            build_time=datetime.fromisoformat(data["build_time"]),
            deployment_environment=data["deployment_environment"],
            deployment_id=data["deployment_id"],
            rollback_target=data.get("rollback_target"),
        )


__all__ = [
    "DeploymentInfo",
    "HealthCheckResult",
    "HealthStatus",
    "PlatformHealth",
    "PlatformInfo",
    "RuntimeContext",
    "classify_status",
]
