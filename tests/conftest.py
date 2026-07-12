from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent tests from picking up the developer's real environment.

    Every `Settings()` construction in a test starts from field defaults
    unless a test explicitly sets an env var itself. This repository never
    commits a real `.env` file (only `.env.example`), so there is no
    on-disk file for `Settings`'s `env_file=".env"` to pick up regardless
    of the test runner's working directory.
    """
    for key in ("ENVIRONMENT", "LOG_LEVEL", "LOG_FORMAT", "APP_NAME"):
        monkeypatch.delenv(key, raising=False)
