"""`build_diagnostic_report` -- composes a `RuntimeContext`, a
`PlatformHealth`, and (optionally) a `DeploymentInfo` into one
`DiagnosticReport`.

Orchestration only, the same role `ops.startup.build_runtime_context`
already plays one layer down: this module defines no new validation or
aggregation logic of its own. It exists so a production investigation
has one function to call -- "what do we currently know about this
process" -- rather than someone hand-assembling three separately
fetched objects under time pressure.
"""

from __future__ import annotations

from common.interfaces import Clock
from common.time import SystemClock
from ops.models import DeploymentInfo, DiagnosticReport, PlatformHealth, RuntimeContext

_DEFAULT_CLOCK: Clock = SystemClock()


def build_diagnostic_report(
    runtime: RuntimeContext,
    health: PlatformHealth,
    *,
    deployment: DeploymentInfo | None = None,
    clock: Clock = _DEFAULT_CLOCK,
) -> DiagnosticReport:
    """Build a `DiagnosticReport` from already-computed `runtime`/
    `health` (and optionally `deployment`). Never computes `runtime` or
    `health` itself -- callers already have them from `ops.startup.
    build_runtime_context` and `ops.health.evaluate_health` respectively,
    and re-deriving either here would risk this report disagreeing with
    the objects it's meant to summarize."""
    return DiagnosticReport(
        runtime_context=runtime,
        health=health,
        deployment_info=deployment,
        generated_at=clock.now(),
    )


__all__ = ["build_diagnostic_report"]
