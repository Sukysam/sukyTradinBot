"""Tests for `ops.secrets`: `EnvSecretSource`, `SecretValue`, and
`resolve_secret`."""

from __future__ import annotations

import pytest

from ops.exceptions import MissingSecretError
from ops.secrets import EnvSecretSource, SecretValue, resolve_secret


class _FakeSecretSource:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, name: str) -> str | None:
        return self._values.get(name)


class TestEnvSecretSource:
    def test_returns_value_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPS_TEST_SECRET", "topsecret")
        assert EnvSecretSource().get("OPS_TEST_SECRET") == "topsecret"

    def test_returns_none_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPS_TEST_SECRET_UNSET", raising=False)
        assert EnvSecretSource().get("OPS_TEST_SECRET_UNSET") is None


class TestSecretValue:
    def test_reveal_returns_actual_value(self) -> None:
        assert SecretValue("topsecret").reveal() == "topsecret"

    def test_repr_is_redacted(self) -> None:
        assert "topsecret" not in repr(SecretValue("topsecret"))
        assert repr(SecretValue("topsecret")) == "SecretValue(***)"

    def test_str_is_redacted(self) -> None:
        assert str(SecretValue("topsecret")) == "***"

    def test_equal_values_are_equal(self) -> None:
        assert SecretValue("a") == SecretValue("a")

    def test_unequal_values_are_not_equal(self) -> None:
        assert SecretValue("a") != SecretValue("b")

    def test_not_equal_to_non_secret_value(self) -> None:
        assert SecretValue("a") != "a"


class TestResolveSecret:
    def test_resolves_present_secret(self) -> None:
        source = _FakeSecretSource({"API_KEY": "abc123"})
        secret = resolve_secret(source, "API_KEY")
        assert secret is not None
        assert secret.reveal() == "abc123"

    def test_raises_when_required_and_missing(self) -> None:
        source = _FakeSecretSource({})
        with pytest.raises(MissingSecretError, match="API_KEY"):
            resolve_secret(source, "API_KEY")

    def test_returns_none_when_optional_and_missing(self) -> None:
        source = _FakeSecretSource({})
        assert resolve_secret(source, "API_KEY", required=False) is None
