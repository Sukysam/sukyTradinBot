"""`build_runtime_context` -- the one startup sequence this platform's
deployment entrypoint is expected to call: load configuration, resolve
and validate required secrets, optionally check subsystem health, then
produce a `RuntimeContext`. Orchestration only -- every step it performs
is a call into a mechanism another `ops` module already owns
(`ops.validation`, `ops.health`); this module defines no new validation
or health logic of its own, the same "startup is a thin wrapper, not a
new algorithm" role WP1's `require_healthy` already established for the
health side of this same sequence.

Deliberately does not load `common.config.Settings` itself --
`environment` arrives as a plain `str` parameter, so `ops` stays free of
`common.config`'s `pydantic`/`pydantic-settings` dependency and every
other `ops` module's "zero transitive third-party dependencies"
property holds for this one too. The caller (a real deployment
entrypoint, not built in this work package) is expected to pass
`Settings().environment`.
"""

from __future__ import annotations

import platform as platform_module
from collections.abc import Sequence

from common.interfaces import Clock
from common.time import SystemClock
from ops.health import evaluate_health, require_healthy
from ops.interfaces import HealthCheck
from ops.models import PlatformInfo, RuntimeContext
from ops.secrets import EnvSecretSource, SecretSource
from ops.validation import require_valid_runtime, validate_runtime

_DEFAULT_CLOCK: Clock = SystemClock()
_DEFAULT_SECRET_SOURCE: SecretSource = EnvSecretSource()


def build_runtime_context(
    *,
    version: str,
    git_commit: str,
    environment: str,
    required_secrets: Sequence[str] = (),
    secret_source: SecretSource = _DEFAULT_SECRET_SOURCE,
    checks: Sequence[HealthCheck] = (),
    python_version: str | None = None,
    clock: Clock = _DEFAULT_CLOCK,
) -> RuntimeContext:
    """Run the full startup sequence and return a `RuntimeContext`.

    Raises `RuntimeValidationError` if `environment` is empty or any
    `required_secrets` entry doesn't resolve via `secret_source`.
    Raises `UnhealthyPlatformError` if `checks` is non-empty and the
    resulting `PlatformHealth` is not `HEALTHY` -- when `checks` is
    empty (the default), the health-check phase is skipped entirely,
    since no real subsystem probes are wired to this function yet; see
    ADR-024.
    """
    result = validate_runtime(
        environment=environment,
        required_secrets=required_secrets,
        secret_source=secret_source,
    )
    require_valid_runtime(result)

    if checks:
        health = evaluate_health(checks, version=version, git_commit=git_commit, clock=clock)
        require_healthy(health)

    now = clock.now()
    platform_info = PlatformInfo(
        version=version,
        git_commit=git_commit,
        build_time=now,
        python_version=python_version or platform_module.python_version(),
    )
    return RuntimeContext(platform_info=platform_info, environment=environment, startup_time=now)


__all__ = ["build_runtime_context"]
