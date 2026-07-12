"""Foundation package: configuration, logging, base interfaces, and common
utilities shared by every future component in this repository.

This package deliberately contains no trading, regime-detection, broker,
or strategy logic — see docs/engineering-handbook/00_MASTER_CHARTER.md's
Milestone 1 scope. It is the chassis other packages are built on top of,
not a component of the trading platform itself.
"""

from __future__ import annotations

from common.config import Settings
from common.errors import AppError, ConfigurationError, RetryExhaustedError
from common.interfaces import Clock, HealthCheck, HealthCheckResult, HealthStatus, Service
from common.io import atomic_write_json, read_json_or_default
from common.logging import configure_logging, get_logger
from common.retry import RetryPolicy, call_with_retry
from common.time import FixedClock, SystemClock, utc_now

__version__ = "0.1.0"

__all__ = [
    "AppError",
    "Clock",
    "ConfigurationError",
    "FixedClock",
    "HealthCheck",
    "HealthCheckResult",
    "HealthStatus",
    "RetryExhaustedError",
    "RetryPolicy",
    "Service",
    "Settings",
    "SystemClock",
    "__version__",
    "atomic_write_json",
    "call_with_retry",
    "configure_logging",
    "get_logger",
    "read_json_or_default",
    "utc_now",
]
