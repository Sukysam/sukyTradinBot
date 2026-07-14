"""Operational Maturity -- Milestone 12, Work Package 1: Health & Readiness.

Not a domain-decision milestone like 1-11, so there is no frozen
contract-freeze PR preceding this implementation -- see
docs/engineering-handbook/Architecture/ADR/ADR-022-Health-And-Readiness-Design.md
for why. `PlatformHealth` is still a small, stable operational model:
`ops.checks` builds one `HealthCheck` per subsystem this platform
depends on (configuration, market data, model artifacts, feature
registry, HMM model, strategy registry, risk service, execution
adapter, memory store, NLP pipeline), `ops.health.evaluate_health`
aggregates them, and `ops.health.require_healthy` is the fail-fast
startup gate built on top of that aggregation.
"""

from __future__ import annotations

from ops.checks import (
    CallableHealthCheck,
    configuration_check,
    execution_adapter_check,
    feature_registry_check,
    hmm_model_check,
    market_data_check,
    memory_store_check,
    model_artifact_check,
    nlp_pipeline_check,
    risk_service_check,
    strategy_registry_check,
)
from ops.exceptions import OpsError, UnhealthyPlatformError
from ops.health import evaluate_health, require_healthy
from ops.interfaces import HealthCheck
from ops.models import HealthCheckResult, HealthStatus, PlatformHealth, classify_status
from ops.reporting import generate_health_report

__version__ = "0.1.0"

__all__ = [
    "CallableHealthCheck",
    "HealthCheck",
    "HealthCheckResult",
    "HealthStatus",
    "OpsError",
    "PlatformHealth",
    "UnhealthyPlatformError",
    "__version__",
    "classify_status",
    "configuration_check",
    "evaluate_health",
    "execution_adapter_check",
    "feature_registry_check",
    "generate_health_report",
    "hmm_model_check",
    "market_data_check",
    "memory_store_check",
    "model_artifact_check",
    "nlp_pipeline_check",
    "require_healthy",
    "risk_service_check",
    "strategy_registry_check",
]
