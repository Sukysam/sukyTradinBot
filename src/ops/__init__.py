"""Operational Maturity -- Milestone 12.

Not a domain-decision milestone like 1-11, so there is no frozen
contract-freeze PR preceding each work package's implementation -- see
docs/engineering-handbook/Architecture/ADR/ADR-022-Health-And-Readiness-Design.md
and ADR-023-Observability-Design.md for why. `PlatformHealth` is the
one stable operational model everything else in this package reads,
never recomputes independently:

- WP1 (Health & Readiness): `ops.checks` builds one `HealthCheck` per
  subsystem this platform depends on (configuration, market data, model
  artifacts, feature registry, HMM model, strategy registry, risk
  service, execution adapter, memory store, NLP pipeline),
  `ops.health.evaluate_health` aggregates them into a `PlatformHealth`,
  and `ops.health.require_healthy` is the fail-fast startup gate built
  on top of that aggregation.
- WP2 (Observability): `ops.metrics` derives exported metrics from a
  `PlatformHealth`; `ops.tracing` gives dependency-injected span
  timing; `ops.logging` emits structured operational log events;
  `ops.alerts` evaluates alert rules against a `PlatformHealth`.
"""

from __future__ import annotations

from ops.alerts import (
    Alert,
    AlertRule,
    AlertSeverity,
    CallableAlertRule,
    degraded_platform_rule,
    evaluate_alerts,
    unhealthy_platform_rule,
)
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
from ops.logging import log_alert, log_health_status
from ops.metrics import (
    Counter,
    Gauge,
    MetricsRegistry,
    export_prometheus_text,
    record_health_metrics,
)
from ops.models import (
    HealthCheckResult,
    HealthStatus,
    PlatformHealth,
    PlatformInfo,
    classify_status,
)
from ops.reporting import generate_health_report
from ops.tracing import Span, Tracer

__version__ = "0.2.0"

__all__ = [
    "Alert",
    "AlertRule",
    "AlertSeverity",
    "CallableAlertRule",
    "CallableHealthCheck",
    "Counter",
    "Gauge",
    "HealthCheck",
    "HealthCheckResult",
    "HealthStatus",
    "MetricsRegistry",
    "OpsError",
    "PlatformHealth",
    "PlatformInfo",
    "Span",
    "Tracer",
    "UnhealthyPlatformError",
    "__version__",
    "classify_status",
    "configuration_check",
    "degraded_platform_rule",
    "evaluate_alerts",
    "evaluate_health",
    "execution_adapter_check",
    "export_prometheus_text",
    "feature_registry_check",
    "generate_health_report",
    "hmm_model_check",
    "log_alert",
    "log_health_status",
    "market_data_check",
    "memory_store_check",
    "model_artifact_check",
    "nlp_pipeline_check",
    "record_health_metrics",
    "require_healthy",
    "risk_service_check",
    "strategy_registry_check",
    "unhealthy_platform_rule",
]
