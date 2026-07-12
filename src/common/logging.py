"""Structured logging setup.

Every module in this repository already follows `logger =
logging.getLogger(__name__)` (see
docs/engineering-handbook/Standards/Python Style Guide.md); this module
supplies the one process-wide `configure_logging()` call that decides how
those log records are actually formatted and where they go, so that
decision is made once, in one place, instead of every module reaching for
its own handler/formatter setup.

Two formats are supported: `"json"` (one JSON object per line — the
production default, so log aggregation can parse fields without regex) and
`"console"` (human-readable, for local development). Which one is active
is driven by `common.config.Settings.log_format`, never hardcoded.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from common.config import LogFormat, Settings

_RESERVED_LOG_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class JSONFormatter(logging.Formatter):
    """Formats each log record as a single-line JSON object.

    Includes standard fields (timestamp, level, logger name, message) plus
    any `extra=` fields passed to the logging call, so structured context
    (e.g. `logger.info("...", extra={"trade_id": trade_id})`) survives into
    the emitted record rather than being flattened into the message string.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_ATTRS
        }
        payload.update(extras)

        return json.dumps(payload, default=str)


def _build_formatter(log_format: LogFormat) -> logging.Formatter:
    if log_format == "json":
        return JSONFormatter()
    if log_format == "console":
        return logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    raise ValueError(f"Unknown log_format {log_format!r}")  # pragma: no cover — Literal-guarded


def configure_logging(settings: Settings | None = None) -> None:
    """Configure the root logger once, at process startup.

    Idempotent: safe to call more than once (e.g. across test setup) —
    clears any handlers a previous call installed rather than stacking
    duplicate handlers, which would otherwise emit every log line once per
    prior call.
    """
    settings = settings or Settings()

    root = logging.getLogger()
    root.setLevel(settings.log_level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_build_formatter(settings.log_format))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Thin convenience wrapper over `logging.getLogger`, for symmetry with
    `configure_logging` — prefer the stdlib call directly
    (`logging.getLogger(__name__)`) inside library modules per this
    repository's existing convention; use this at application entry points
    where importing all of `logging` for one call feels heavier than
    necessary.
    """
    return logging.getLogger(name)


__all__ = ["JSONFormatter", "configure_logging", "get_logger"]
