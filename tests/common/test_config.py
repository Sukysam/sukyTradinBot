from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from common.config import DEFAULT_ENVIRONMENT, DEFAULT_LOG_FORMAT, Settings, load_yaml_config
from common.errors import ConfigurationError


def test_settings_defaults_are_safe() -> None:
    settings = Settings()
    assert settings.environment == DEFAULT_ENVIRONMENT
    assert settings.environment != "production"
    assert settings.log_format == DEFAULT_LOG_FORMAT


def test_settings_is_production_true_only_for_production_environment() -> None:
    assert Settings(environment="production").is_production is True
    assert Settings(environment="development").is_production is False
    assert Settings(environment="test").is_production is False


def test_settings_reads_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LOG_FORMAT", "console")

    settings = Settings()

    assert settings.environment == "production"
    assert settings.log_level == "WARNING"
    assert settings.log_format == "console"


def test_settings_rejects_invalid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging-typo")
    with pytest.raises(ValueError):
        Settings()


def test_settings_is_frozen() -> None:
    settings = Settings()
    with pytest.raises(ValidationError, match="frozen"):
        settings.environment = "production"


def test_load_yaml_config_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    assert load_yaml_config(tmp_path / "does-not-exist.yaml") == {}


def test_load_yaml_config_empty_file_returns_empty_dict(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    assert load_yaml_config(path) == {}


def test_load_yaml_config_parses_mapping(tmp_path: Path) -> None:
    path = tmp_path / "app.yaml"
    path.write_text("app_name: my-app\nlog_level: DEBUG\n", encoding="utf-8")

    result = load_yaml_config(path)

    assert result == {"app_name": "my-app", "log_level": "DEBUG"}


def test_load_yaml_config_rejects_non_mapping_top_level(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="mapping"):
        load_yaml_config(path)
