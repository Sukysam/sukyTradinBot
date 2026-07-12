from __future__ import annotations

import json
import logging
import sys

import pytest

from common.config import Settings
from common.logging import JSONFormatter, configure_logging, get_logger


def _make_record(
    msg: str = "hello", level: int = logging.INFO, extra: dict[str, object] | None = None
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


def test_json_formatter_produces_valid_json_with_core_fields() -> None:
    formatter = JSONFormatter()
    record = _make_record("hello world")

    parsed = json.loads(formatter.format(record))

    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert "timestamp" in parsed


def test_json_formatter_includes_extra_fields() -> None:
    formatter = JSONFormatter()
    record = _make_record("trade event", extra={"trade_id": "abc123", "notional": 100.0})

    parsed = json.loads(formatter.format(record))

    assert parsed["trade_id"] == "abc123"
    assert parsed["notional"] == 100.0


def test_json_formatter_includes_exception_info() -> None:
    formatter = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record("failed")
        record.exc_info = sys.exc_info()

    parsed = json.loads(formatter.format(record))

    assert "ValueError: boom" in parsed["exception"]


def test_configure_logging_is_idempotent_and_sets_level(caplog: pytest.LogCaptureFixture) -> None:
    configure_logging(Settings(log_level="WARNING", log_format="console"))
    configure_logging(Settings(log_level="WARNING", log_format="console"))

    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert root.level == logging.WARNING


def test_configure_logging_json_format_installs_json_formatter() -> None:
    configure_logging(Settings(log_format="json"))

    root = logging.getLogger()
    assert isinstance(root.handlers[0].formatter, JSONFormatter)


def test_get_logger_returns_stdlib_logger() -> None:
    logger = get_logger("my.module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "my.module"
