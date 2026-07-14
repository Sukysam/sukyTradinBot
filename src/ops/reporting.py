"""`generate_health_report`/`generate_diagnostic_report` -- minimal,
human-readable text summaries of a `PlatformHealth`/`DiagnosticReport`.
Consume the model, never shape it. Not a frozen contract itself: these
are renderings, free to change shape without an ADR.
"""

from __future__ import annotations

from ops.models import DiagnosticReport, PlatformHealth


def generate_health_report(health: PlatformHealth) -> str:
    lines = [
        f"Platform Health Report -- {health.status.value.upper()}",
        f"  version:      {health.version}",
        f"  git_commit:   {health.git_commit}",
        f"  timestamp:    {health.timestamp.isoformat()}",
        "",
        "  checks:",
    ]
    for check in health.checks:
        marker = "OK" if check.healthy else "FAIL"
        lines.append(f"    [{marker}] {check.name}: {check.detail}")
    return "\n".join(lines)


def generate_diagnostic_report(report: DiagnosticReport) -> str:
    runtime = report.runtime_context
    lines = [
        f"Diagnostic Report -- generated {report.generated_at.isoformat()}",
        "",
        "  version summary:",
        f"    version:       {runtime.platform_info.version}",
        f"    git_commit:    {runtime.platform_info.git_commit}",
        f"    build_time:    {runtime.platform_info.build_time.isoformat()}",
        f"    python:        {runtime.platform_info.python_version}",
        "",
        "  environment summary:",
        f"    environment:   {runtime.environment}",
        f"    startup_time:  {runtime.startup_time.isoformat()}",
        "",
        "  deployment summary:",
    ]
    if report.deployment_info is None:
        lines.append("    (no deployment tracking available)")
    else:
        deployment = report.deployment_info
        lines.append(f"    deployment_id: {deployment.deployment_id}")
        lines.append(f"    environment:   {deployment.deployment_environment}")
        lines.append(f"    rollback_target: {deployment.rollback_target or '(none)'}")
    lines.append("")
    lines.append("  health summary:")
    lines.append(f"    status:        {report.health.status.value.upper()}")
    for check in report.health.checks:
        marker = "OK" if check.healthy else "FAIL"
        lines.append(f"      [{marker}] {check.name}: {check.detail}")
    return "\n".join(lines)


__all__ = ["generate_diagnostic_report", "generate_health_report"]
