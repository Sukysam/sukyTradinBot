"""Structured *operational event* logging: health-status transitions and
alert firings, emitted with a consistent schema.

Builds on `common.logging`'s existing JSON formatter rather than
parallel infrastructure -- this module does not call
`logging.basicConfig`, install a handler, or otherwise reconfigure
logging; `common.logging.configure_logging` remains the one place that
happens. It only defines what an operational event log record looks
like and hands it to a caller-supplied `logging.Logger`, the same
dependency-injection convention every other `ops` module follows.
"""

from __future__ import annotations

import logging

from ops.alerts import Alert
from ops.models import PlatformHealth


def log_health_status(logger: logging.Logger, health: PlatformHealth) -> None:
    """Log one structured `health_status` event for `health`."""
    failing = [check.name for check in health.checks if not check.healthy]
    logger.info(
        "platform health status: %s",
        health.status.value,
        extra={
            "event": "health_status",
            "status": health.status.value,
            "version": health.version,
            "git_commit": health.git_commit,
            "failing_checks": failing,
        },
    )


def log_alert(logger: logging.Logger, alert: Alert) -> None:
    """Log one structured `alert_fired` event for `alert`."""
    logger.warning(
        "alert fired: %s (%s)",
        alert.name,
        alert.severity.value,
        extra={
            "event": "alert_fired",
            "alert": alert.name,
            "severity": alert.severity.value,
            "detail": alert.detail,
        },
    )


__all__ = ["log_alert", "log_health_status"]
