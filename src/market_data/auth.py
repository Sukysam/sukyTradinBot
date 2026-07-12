"""Alpaca credential loading.

Mirrors the exact environment variable names
`regime-trader/main.py` already reads directly via `os.environ`
(`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER`) — see
docs/engineering-handbook/12_DEVOPS_ENGINEER.md's environment/secrets
contract — so introducing this typed loader doesn't create a second,
differently-named way to configure the same credentials. `ALPACA_PAPER`
defaults to `True`: an unset value must never silently mean live trading,
matching `main.py`'s existing default and
docs/engineering-handbook/00_MASTER_CHARTER.md invariant #8.
"""

from __future__ import annotations

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from market_data.errors import ProviderAuthenticationError


class AlpacaCredentials(BaseSettings):
    """Alpaca API credentials, loaded from environment variables (or a
    `.env` file). Construct via `load_alpaca_credentials()`, not directly,
    so a missing/invalid credential raises
    `market_data.errors.ProviderAuthenticationError` rather than a raw
    `pydantic.ValidationError` — see that function's docstring.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    api_key: str = Field(validation_alias="ALPACA_API_KEY")
    secret_key: str = Field(validation_alias="ALPACA_SECRET_KEY")
    paper: bool = Field(default=True, validation_alias="ALPACA_PAPER")


def load_alpaca_credentials() -> AlpacaCredentials:
    """Load `AlpacaCredentials` from the environment.

    Raises `ProviderAuthenticationError` (never a raw
    `pydantic.ValidationError`) if `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`
    are missing — this is the single point where this package translates
    "credentials are wrong" into its own exception hierarchy, per
    `errors.py`'s docstring.
    """
    try:
        return AlpacaCredentials()  # type: ignore[call-arg]  # fields load from env, not kwargs
    except ValidationError as exc:
        raise ProviderAuthenticationError(
            f"Missing or invalid Alpaca credentials (expected ALPACA_API_KEY and "
            f"ALPACA_SECRET_KEY environment variables): {exc}"
        ) from exc


__all__ = ["AlpacaCredentials", "load_alpaca_credentials"]
