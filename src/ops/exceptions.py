"""Exception hierarchy for operational tooling.

All derive from `OpsError` (itself an `AppError`), matching the same
"catch specific exceptions, fail loudly, never swallow silently" pattern
every other package in this platform follows.
"""

from __future__ import annotations

from common.errors import AppError


class OpsError(AppError):
    """Base class for all errors raised by `ops`."""


class UnhealthyPlatformError(OpsError):
    """Raised by `ops.health.require_healthy` when a `PlatformHealth`
    report is not `HealthStatus.HEALTHY` -- the fail-fast startup gate.
    Never caught and silently ignored by production start-up code; a
    process that starts anyway despite a failing dependency check is
    exactly the "silently no-op" failure mode
    [00_MASTER_CHARTER.md](../../docs/engineering-handbook/00_MASTER_CHARTER.md)
    invariant #4 exists to prevent."""


class MissingSecretError(OpsError):
    """Raised by `ops.secrets.resolve_secret` when a required secret is
    not present in the injected `SecretSource`. Never carries the
    secret's own value -- only its name -- since an exception message is
    exactly the kind of thing that ends up in a log or a bug tracker."""


class RuntimeValidationError(OpsError):
    """Raised by `ops.validation.require_valid_runtime` when a
    `ValidationResult` is not valid -- the fail-fast startup gate for
    configuration/secrets, the same role `UnhealthyPlatformError` plays
    for health checks."""


class DeploymentValidationError(OpsError):
    """Raised by `ops.deployment.require_valid_deployment` when a
    `ValidationResult` produced by `validate_deployment` or
    `verify_release_manifest` is not valid -- the fail-fast gate that
    stops a release before it proceeds, the same role
    `RuntimeValidationError` plays for startup."""


class NoRollbackTargetError(OpsError):
    """Raised by `ops.rollback.require_rollback_target` when no prior
    deployment is available to roll back to. A rollback attempted with
    nothing to roll back to is exactly the kind of silent-no-op this
    codebase's exceptions exist to prevent -- it must fail loudly, not
    proceed as if the rollback happened."""


__all__ = [
    "DeploymentValidationError",
    "MissingSecretError",
    "NoRollbackTargetError",
    "OpsError",
    "RuntimeValidationError",
    "UnhealthyPlatformError",
]
