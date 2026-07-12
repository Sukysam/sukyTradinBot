from __future__ import annotations

from common.errors import AppError, ConfigurationError, RetryExhaustedError


def test_configuration_error_is_an_app_error() -> None:
    assert issubclass(ConfigurationError, AppError)


def test_retry_exhausted_error_is_an_app_error() -> None:
    assert issubclass(RetryExhaustedError, AppError)


def test_app_error_is_a_plain_exception() -> None:
    assert issubclass(AppError, Exception)


def test_configuration_error_carries_message() -> None:
    try:
        raise ConfigurationError("missing FOO env var")
    except ConfigurationError as exc:
        assert "missing FOO env var" in str(exc)
