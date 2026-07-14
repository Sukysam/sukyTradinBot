"""Generic, injectable secret resolution.

`SecretSource` is a Protocol so `ops.validation`/`ops.startup` never
depend on *how* a secret is stored -- `EnvSecretSource` reads
`os.environ`, the same source `common.config.Settings` and
`market_data.auth.AlpacaCredentials` already read credentials from, so
this doesn't introduce a second, competing convention for where secrets
live. No Vault/AWS Secrets Manager client: no secret backend has been
chosen for this platform yet, and adding one now would commit to a
vendor ahead of that decision -- the same reasoning
ADR-023 gave for deferring a real tracing-SDK integration. Swapping in
a real backend later means writing one new `SecretSource`
implementation, not touching any call site that already resolves
secrets through this Protocol.

`SecretValue` exists so a resolved secret can be passed around,
returned from a function, or held on an object without ever being
accidentally logged, printed, or included in an exception message --
`repr()`/`str()` are redacted; `reveal()` is the one explicit,
impossible-to-typo-into-a-log-call way to read the actual value.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from ops.exceptions import MissingSecretError


@runtime_checkable
class SecretSource(Protocol):
    """Resolves a secret by name, or returns `None` if it isn't set."""

    def get(self, name: str) -> str | None: ...


class EnvSecretSource:
    """A `SecretSource` backed by process environment variables."""

    def get(self, name: str) -> str | None:
        return os.environ.get(name)


class SecretValue:
    """Wraps a resolved secret value. Deliberately not a `dataclass` --
    a `dataclass`'s auto-generated `__repr__` would print the field
    value, exactly what this class exists to prevent."""

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """Return the actual secret value. Named to make every call
        site that needs the real value grep-able and deliberate."""
        return self._value

    def __repr__(self) -> str:
        return "SecretValue(***)"

    def __str__(self) -> str:
        return "***"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SecretValue):
            return NotImplemented
        return self._value == other._value


def resolve_secret(source: SecretSource, name: str, *, required: bool = True) -> SecretValue | None:
    """Resolve secret `name` from `source`.

    Raises `MissingSecretError` if `required` and `name` isn't set;
    returns `None` (never raises) if not `required` and `name` isn't
    set, so an optional secret's absence is a normal, checkable
    outcome rather than an exception a caller has to catch.
    """
    raw = source.get(name)
    if raw is None:
        if required:
            raise MissingSecretError(f"required secret {name!r} was not found")
        return None
    return SecretValue(raw)


__all__ = ["EnvSecretSource", "SecretSource", "SecretValue", "resolve_secret"]
