"""Operational Maturity -- Milestone 12.

Not a domain-decision milestone like 1-11, so there is no frozen
contract-freeze PR preceding each work package's implementation -- see
docs/engineering-handbook/Architecture/ADR/ADR-022-Health-And-Readiness-Design.md,
ADR-023-Observability-Design.md, and ADR-024-Configuration-And-Secrets-Design.md
for why. `PlatformHealth` is the one stable operational model everything
else in this package reads, never recomputes independently:

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
- WP3 (Configuration & Secrets): `ops.secrets` gives injectable secret
  resolution (`SecretSource`/`EnvSecretSource`/`SecretValue`);
  `ops.validation` is the fail-fast gate for environment/secret
  configuration, mirroring `ops.health`'s report/gate split;
  `ops.startup.build_runtime_context` composes configuration
  validation, secret resolution, and (optionally) health checks into
  one immutable `RuntimeContext` -- this platform's operational runtime
  identity.
- WP4 (Deployment & Release Automation): `ops.models.DeploymentInfo`
  describes one deployment instance, distinct from `PlatformInfo` (the
  build); `ops.deployment` validates a `DeploymentInfo` against a
  `RuntimeContext` and verifies release-artifact checksums via
  `ReleaseManifest`; `ops.rollback.select_rollback_target` picks the
  last-known-good prior deployment from history. No CI/CD platform
  integration -- no deployment target has been chosen yet; see
  ADR-025-Deployment-And-Release-Automation-Design.md.
- WP5 (Operations & Diagnostics): `ops.models.DiagnosticReport`
  composes an already-built `RuntimeContext`, `PlatformHealth`, and
  optional `DeploymentInfo` into one snapshot for production
  investigation; `ops.diagnostics.build_diagnostic_report` is pure
  composition (no new validation logic); `ops.reporting.
  generate_diagnostic_report` renders it as text. Runbooks/incident-
  response/disaster-recovery/backup-restore/on-call/production-
  readiness procedures live in `docs/operations/`, outside `src/`, per
  direct instruction; see ADR-026-Operations-And-Diagnostics-Design.md.
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
from ops.deployment import (
    ReleaseManifest,
    compute_checksum,
    require_valid_deployment,
    validate_deployment,
    verify_release_manifest,
)
from ops.diagnostics import build_diagnostic_report
from ops.exceptions import (
    DeploymentValidationError,
    MissingSecretError,
    NoRollbackTargetError,
    OpsError,
    RuntimeValidationError,
    UnhealthyPlatformError,
)
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
    DeploymentInfo,
    DiagnosticReport,
    HealthCheckResult,
    HealthStatus,
    PlatformHealth,
    PlatformInfo,
    RuntimeContext,
    classify_status,
)
from ops.reporting import generate_diagnostic_report, generate_health_report
from ops.rollback import require_rollback_target, select_rollback_target
from ops.secrets import EnvSecretSource, SecretSource, SecretValue, resolve_secret
from ops.startup import build_runtime_context
from ops.tracing import Span, Tracer
from ops.validation import ValidationResult, require_valid_runtime, validate_runtime

__version__ = "0.5.0"

__all__ = [
    "Alert",
    "AlertRule",
    "AlertSeverity",
    "CallableAlertRule",
    "CallableHealthCheck",
    "Counter",
    "DeploymentInfo",
    "DeploymentValidationError",
    "DiagnosticReport",
    "EnvSecretSource",
    "Gauge",
    "HealthCheck",
    "HealthCheckResult",
    "HealthStatus",
    "MetricsRegistry",
    "MissingSecretError",
    "NoRollbackTargetError",
    "OpsError",
    "PlatformHealth",
    "PlatformInfo",
    "ReleaseManifest",
    "RuntimeContext",
    "RuntimeValidationError",
    "SecretSource",
    "SecretValue",
    "Span",
    "Tracer",
    "UnhealthyPlatformError",
    "ValidationResult",
    "__version__",
    "build_diagnostic_report",
    "build_runtime_context",
    "classify_status",
    "compute_checksum",
    "configuration_check",
    "degraded_platform_rule",
    "evaluate_alerts",
    "evaluate_health",
    "execution_adapter_check",
    "export_prometheus_text",
    "feature_registry_check",
    "generate_diagnostic_report",
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
    "require_rollback_target",
    "require_valid_deployment",
    "require_valid_runtime",
    "resolve_secret",
    "risk_service_check",
    "select_rollback_target",
    "strategy_registry_check",
    "unhealthy_platform_rule",
    "validate_deployment",
    "validate_runtime",
    "verify_release_manifest",
]
