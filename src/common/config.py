"""Application configuration and environment handling.

`Settings` is the single source of truth for process-level configuration:
what environment this process is running in, and how it should log. It is
intentionally generic — no trading-domain fields (no ticker lists, no
broker credentials, no risk thresholds) belong here. Per
docs/engineering-handbook/Architecture/Known Gaps.md item 1,
`config/settings.yaml` (the trading-specific ticker/sector configuration
`regime-trader/main.py` still lacks) is a separate, not-yet-built concern
owned by System Architect / Technical Planner; this module only builds the
underlying mechanism — env-var and `.env` loading via `pydantic-settings`,
plus a small YAML-file loader — that a trading-specific settings module
can be layered on top of later without redoing this plumbing.

Precedence (highest wins), per `pydantic-settings` defaults: constructor
arguments > environment variables > `.env` file > field defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.errors import ConfigurationError

Environment = Literal["development", "test", "production"]
LogFormat = Literal["json", "console"]

# Safe-by-default: an unset ENVIRONMENT must never silently behave like
# production. See docs/engineering-handbook/00_MASTER_CHARTER.md Definition
# of Done #7 ("any new configuration defaults to the safer option").
DEFAULT_ENVIRONMENT: Environment = "development"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT: LogFormat = "json"


class Settings(BaseSettings):
    """Process-level application settings, loaded from environment
    variables (optionally via a `.env` file) with validation.

    Example:
        settings = Settings()  # reads ENVIRONMENT, LOG_LEVEL, ... from env
        settings = Settings(environment="test")  # explicit override, e.g. in tests
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Environment = Field(default=DEFAULT_ENVIRONMENT)
    log_level: str = Field(default=DEFAULT_LOG_LEVEL)
    log_format: LogFormat = Field(default=DEFAULT_LOG_FORMAT)
    app_name: str = Field(default="regime-trader")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def load_yaml_config(path: Path) -> dict[str, Any]:
    """Load a non-secret, structured config file (e.g. `config/app.yaml`).

    Returns an empty dict if the file doesn't exist — an absent optional
    config file is a valid "use defaults" state, not an error, matching
    this repository's existing load-or-init convention for state files.
    Raises `ConfigurationError` if the file exists but doesn't parse to a
    mapping at the top level, since a config file that parses to a list or
    scalar is almost certainly a mistake worth failing loudly on rather
    than silently ignoring.

    Secrets never belong in a file loaded by this function — see
    docs/engineering-handbook/Standards/Coding Standards.md's "Security &
    secrets" section. Use environment variables (`Settings` above) for
    anything sensitive.
    """
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigurationError(
            f"Expected {path} to contain a YAML mapping at the top level, "
            f"got {type(raw).__name__}"
        )
    return raw


__all__ = [
    "DEFAULT_ENVIRONMENT",
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_LOG_LEVEL",
    "Environment",
    "LogFormat",
    "Settings",
    "load_yaml_config",
]
