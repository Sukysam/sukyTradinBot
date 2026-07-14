"""`generate_health_report` -- a minimal, human-readable text summary of
a `PlatformHealth` report. Consumes the model, never shapes it. Not a
frozen contract itself: this is a rendering, free to change shape
without an ADR.
"""

from __future__ import annotations

from ops.models import PlatformHealth


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


__all__ = ["generate_health_report"]
