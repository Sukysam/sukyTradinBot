"""Tests for `ops.validation`: `ValidationResult`, `validate_runtime`,
and `require_valid_runtime`."""

from __future__ import annotations

import pytest

from ops.exceptions import RuntimeValidationError
from ops.validation import ValidationResult, require_valid_runtime, validate_runtime


class _FakeSecretSource:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, name: str) -> str | None:
        return self._values.get(name)


class TestValidationResult:
    def test_rejects_valid_with_errors(self) -> None:
        with pytest.raises(ValueError, match="valid=True"):
            ValidationResult(valid=True, errors=("oops",))

    def test_rejects_invalid_without_errors(self) -> None:
        with pytest.raises(ValueError, match="valid=False"):
            ValidationResult(valid=False, errors=())

    def test_allows_valid_with_no_errors(self) -> None:
        result = ValidationResult(valid=True, errors=())
        assert result.valid is True

    def test_allows_invalid_with_errors(self) -> None:
        result = ValidationResult(valid=False, errors=("oops",))
        assert result.valid is False


class TestValidateRuntime:
    def test_valid_when_environment_set_and_no_required_secrets(self) -> None:
        result = validate_runtime(environment="production", secret_source=_FakeSecretSource({}))
        assert result.valid is True
        assert result.errors == ()

    def test_invalid_when_environment_empty(self) -> None:
        result = validate_runtime(environment="", secret_source=_FakeSecretSource({}))
        assert result.valid is False
        assert any("environment" in error for error in result.errors)

    def test_invalid_when_required_secret_missing(self) -> None:
        result = validate_runtime(
            environment="production",
            required_secrets=["API_KEY"],
            secret_source=_FakeSecretSource({}),
        )
        assert result.valid is False
        assert any("API_KEY" in error for error in result.errors)

    def test_valid_when_required_secret_present(self) -> None:
        result = validate_runtime(
            environment="production",
            required_secrets=["API_KEY"],
            secret_source=_FakeSecretSource({"API_KEY": "abc"}),
        )
        assert result.valid is True

    def test_collects_multiple_errors(self) -> None:
        result = validate_runtime(
            environment="",
            required_secrets=["API_KEY", "SECRET_KEY"],
            secret_source=_FakeSecretSource({}),
        )
        assert len(result.errors) == 3


class TestRequireValidRuntime:
    def test_does_not_raise_when_valid(self) -> None:
        require_valid_runtime(ValidationResult(valid=True, errors=()))

    def test_raises_with_joined_errors_when_invalid(self) -> None:
        result = ValidationResult(valid=False, errors=("missing A", "missing B"))
        with pytest.raises(RuntimeValidationError, match="missing A; missing B"):
            require_valid_runtime(result)
