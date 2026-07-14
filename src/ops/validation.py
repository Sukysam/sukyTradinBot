"""Fail-fast startup validation over environment identity and required
secrets.

`validate_runtime` answers a question and returns a `ValidationResult`;
it does not raise and does not act on the answer -- the same
"report, don't act" split `ops.health.evaluate_health` already
established relative to `require_healthy`. `require_valid_runtime` is
the corresponding gate, mirroring `require_healthy` exactly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ops.exceptions import RuntimeValidationError
from ops.secrets import SecretSource


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of one `validate_runtime` call. `errors` is empty
    iff `valid` is `True` -- cross-checked at construction so the two
    can never silently disagree, the same pattern `PlatformHealth.status`
    carries relative to its own `checks`."""

    valid: bool
    errors: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.valid and self.errors:
            raise ValueError("valid=True but errors is non-empty")
        if not self.valid and not self.errors:
            raise ValueError("valid=False but errors is empty")


def validate_runtime(
    *,
    environment: str,
    required_secrets: Sequence[str] = (),
    secret_source: SecretSource,
) -> ValidationResult:
    """Validate that `environment` is set and every name in
    `required_secrets` resolves via `secret_source`. Collects every
    failure rather than stopping at the first, so a caller sees the
    full set of problems in one pass instead of fixing them one at a
    time across repeated restarts."""
    errors: list[str] = []
    if not environment:
        errors.append("environment must not be empty")
    for name in required_secrets:
        if secret_source.get(name) is None:
            errors.append(f"missing required secret: {name}")
    return ValidationResult(valid=not errors, errors=tuple(errors))


def require_valid_runtime(result: ValidationResult) -> None:
    """Raise `RuntimeValidationError` unless `result.valid`."""
    if not result.valid:
        raise RuntimeValidationError("; ".join(result.errors))


__all__ = ["ValidationResult", "require_valid_runtime", "validate_runtime"]
