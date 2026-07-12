from __future__ import annotations

import pytest

from market_data.auth import AlpacaCredentials, load_alpaca_credentials
from market_data.errors import ProviderAuthenticationError


@pytest.fixture(autouse=True)
def _clear_alpaca_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_PAPER"):
        monkeypatch.delenv(key, raising=False)


def test_load_credentials_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key123")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret456")

    creds = load_alpaca_credentials()

    assert creds.api_key == "key123"
    assert creds.secret_key == "secret456"


def test_paper_defaults_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key123")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret456")

    creds = load_alpaca_credentials()

    assert creds.paper is True


def test_paper_false_when_explicitly_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key123")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret456")
    monkeypatch.setenv("ALPACA_PAPER", "false")

    creds = load_alpaca_credentials()

    assert creds.paper is False


def test_missing_credentials_raise_provider_authentication_error() -> None:
    with pytest.raises(ProviderAuthenticationError, match="ALPACA_API_KEY"):
        load_alpaca_credentials()


def test_missing_only_secret_key_raises() -> None:
    import os

    os.environ["ALPACA_API_KEY"] = "key123"
    try:
        with pytest.raises(ProviderAuthenticationError):
            load_alpaca_credentials()
    finally:
        del os.environ["ALPACA_API_KEY"]


def test_credentials_are_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key123")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret456")
    creds = AlpacaCredentials()  # type: ignore[call-arg]

    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="frozen"):
        creds.api_key = "changed"
