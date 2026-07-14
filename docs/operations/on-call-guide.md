# On-Call Guide

Who gets paged, how they check status, and where they escalate. Read
this first; it links out to the detailed procedures rather than
repeating them.

## What pages on-call

From [SOPs/Incident Response Runbook.md](../engineering-handbook/SOPs/Incident%20Response%20Runbook.md)
(trading-domain, highest priority — capital is at risk):

- Circuit breaker daily/weekly halt (class 2)
- Emergency hard stop (class 3) — **highest severity**
- Liquidation failure (class 4) — **highest severity**

From [Incident Response — Operational Layer](incident-response.md)
(platform-domain, added by Milestone 12):

- `platform_unhealthy` alert (`ops.alerts.unhealthy_platform_rule`,
  `CRITICAL`) — page immediately, same urgency tier as a trading-domain
  `CRITICAL`.
- `platform_degraded` alert (`ops.alerts.degraded_platform_rule`,
  `WARNING`) — investigate promptly, page only if it persists or
  involves `risk_service`/`execution_adapter` specifically (see
  [Incident Response](incident-response.md) class 2).
- `RuntimeValidationError`/`DeploymentValidationError` during a release
  — pages the release owner, not general on-call, unless it occurs
  outside a planned release window (which is itself suspicious and
  worth escalating as its own incident).
- `NoRollbackTargetError` — pages immediately; a deployment that can't
  be rolled back needs a human decision right away.

## First thing to check: the diagnostic report

Before doing anything else, get the current picture:

```python
report = ops.diagnostics.build_diagnostic_report(runtime_context, health, deployment=deployment_info)
print(ops.reporting.generate_diagnostic_report(report))
```

This prints version, environment, deployment (if tracked), and every
health check's current status in one place — the same object every
`docs/operations/` procedure expects you to have open before doing
anything else.

If a `RuntimeContext`/`PlatformHealth` isn't already available (e.g.
you're responding cold, not from an existing monitoring loop),
`ops.health.evaluate_health` against real subsystem checks gives you
`health`; `ops.startup.build_runtime_context` gives you `runtime` (but
don't re-run this against a live production process without
understanding what it does — see
[Release Runbook](release-runbook.md) before treating startup
validation as a read-only diagnostic step).

## Escalation path

1. **On-call engineer** — first responder for any page above. Has
   access to run the diagnostic report and the read-only checks in
   [Incident Response](incident-response.md).
2. **[08 Risk Manager](../engineering-handbook/08_RISK_MANAGER.md)** —
   required sign-off before clearing `risk_manager.EMERGENCY_HALT.lock`
   (per the existing SOP's class 3) or before resuming trading after
   any incident that touched the risk/execution path.
3. **[12 DevOps Engineer](../engineering-handbook/12_DEVOPS_ENGINEER.md)** —
   owns process-supervision and platform-health incidents specifically
   (the new WP1–WP4 incident classes), and the release/rollback
   procedures in [Release Runbook](release-runbook.md).
4. **[02 Technical Planner](../engineering-handbook/02_TECHNICAL_PLANNER.md)** —
   escalation target for anything indicating a release-process failure
   (an unclosed Known Gap reaching production, a repeated deployment
   drift) rather than a one-off operational event.

## Severity quick reference

| Severity | Examples | Response |
|---|---|---|
| Highest (page immediately, all hands) | Emergency hard stop, liquidation failure, `platform_unhealthy`, `NoRollbackTargetError` | Page on-call now; Risk Manager sign-off required before resuming if trading-domain |
| High (investigate promptly) | Circuit breaker daily/weekly halt, `platform_degraded` persisting or on `risk_service`/`execution_adapter` | Page on-call; written incident report within 24 hours |
| Routine (log, don't page) | Circuit breaker size cut, `platform_degraded` on a non-critical check, resolved on next tick/check | Note in incident log; trend over time |

## Before you page someone else

Confirm you've actually read the diagnostic report and the relevant
procedure ([Incident Response](incident-response.md),
[Release Runbook](release-runbook.md), or
[Disaster Recovery](disaster-recovery.md)) — most of what reaches
on-call has a documented first step above. Paging without that context
costs the next responder time re-deriving what the diagnostic report
would have told you in one call.
