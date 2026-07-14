# Incident Response — Operational Layer

Complements, does not replace,
[SOPs/Incident Response Runbook.md](../engineering-handbook/SOPs/Incident%20Response%20Runbook.md).
That document covers trading-domain incidents (circuit breaker halts,
emergency hard stop, liquidation failure) ported from the legacy
`regime-trader/core/risk_manager.py` into `src/risk`/`src/execution` —
those incident classes and their severity/escalation are unchanged and
still the primary reference for anything capital-at-risk. This
document adds the incident classes `src/ops` (Milestone 12) can now
detect, none of which existed before WP1–WP4.

## Incident classes

### 1. Startup validation failure (`RuntimeValidationError`)

- **Signal**: `ops.startup.build_runtime_context` raises
  `RuntimeValidationError` — the process never starts.
- **Immediate action**: none required for capital — no process is
  running, so nothing can trade in an unvalidated state (this is the
  fail-fast gate working as intended, not a failure of it). Read the
  exception message: it names every missing/invalid item in one pass
  (`ops.validation.validate_runtime` collects all errors, not just the
  first).
- **Follow-up**: fix the named environment/secret problem and retry.
  If this happens during an automated deploy, treat it as a release
  failure per [Release Runbook](release-runbook.md), not a silent
  retry loop.

### 2. Platform unhealthy or degraded during runtime

- **Signal**: `ops.health.evaluate_health` produces a `PlatformHealth`
  with `status` `DEGRADED` or `UNHEALTHY`; if `ops.alerts` rules are
  wired to a monitoring loop, `platform_degraded` (`WARNING`) or
  `platform_unhealthy` (`CRITICAL`) fires — see
  [ADR-023](../engineering-handbook/Architecture/ADR/ADR-023-Observability-Design.md).
- **Immediate action**: run `ops.reporting.generate_health_report(health)`
  (or, for a fuller picture, `ops.diagnostics.build_diagnostic_report`
  + `generate_diagnostic_report`) and read which named check(s) are
  failing (`configuration`, `market_data`, `model_artifact`,
  `feature_registry`, `hmm_model`, `strategy_registry`, `risk_service`,
  `execution_adapter`, `memory_store`, `nlp_pipeline` — see
  [ADR-022](../engineering-handbook/Architecture/ADR/ADR-022-Health-And-Readiness-Design.md)).
  `UNHEALTHY` (every check failing) escalates faster than `DEGRADED`
  (some checks failing) — a single failing check rarely means trading
  itself is unsafe, but `risk_service`/`execution_adapter` failing
  specifically should be treated with the same urgency as a circuit
  breaker halt, since it means the veto layer or order path may not be
  reachable.
- **Follow-up**: root-cause the specific failing check's `detail`
  message (`CallableHealthCheck.check()` never returns an empty
  detail — see ADR-022), fix the underlying subsystem, confirm health
  returns to `HEALTHY` before considering the incident closed.

### 3. Deployment/runtime drift (`DeploymentValidationError`)

- **Signal**: `ops.deployment.validate_deployment` reports a
  `version`/`git_commit` mismatch between a `DeploymentInfo` and the
  `RuntimeContext` it's supposed to describe.
- **Immediate action**: this means "what we think is running" and
  "what's actually running" disagree — treat as a release-process
  failure, not a code bug. Do not assume either side is correct without
  checking; confirm the actual running build's `git_commit` directly.
- **Follow-up**: identify how the deployment record and the running
  process diverged (a failed or partial deploy, a manual process
  restart that bypassed the release runbook, stale deployment history)
  and fix the release process, not just this one incident.

### 4. Release-artifact checksum mismatch

- **Signal**: `ops.deployment.verify_release_manifest` reports one or
  more artifact checksum mismatches or missing artifacts.
- **Immediate action**: stop the release (see
  [Release Runbook](release-runbook.md) step 2) — do not deploy an
  artifact that doesn't match what was recorded at build time. Treat as
  a potential integrity issue (corrupted transfer, wrong artifact,
  tampering) until proven otherwise, not routine flakiness.
- **Follow-up**: rebuild and re-verify from source rather than
  attempting to "fix" a mismatched artifact in place.

### 5. Rollback with no target (`NoRollbackTargetError`)

- **Signal**: `ops.rollback.require_rollback_target` raises because
  `select_rollback_target` found no prior deployment to roll back to.
- **Immediate action**: this means the current deployment cannot be
  automatically undone — escalate immediately per
  [On-Call Guide](on-call-guide.md) rather than attempting a manual
  rollback without a known-good reference point.
- **Follow-up**: after resolution, confirm deployment history is being
  recorded correctly so this doesn't recur on the next release.

## General incident write-up template

Use the same template as the existing SOP's, for consistency across
both incident classes:

```
## Incident: <one line>
Detected: <timestamp> via <log line / alert / health check>
Severity: <class from above, or from the legacy SOP if trading-domain>
DiagnosticReport at detection: <output of generate_diagnostic_report>
Timeline: <what happened, in order>
Root cause: <or "investigation ongoing">
Resolution: <what was done>
Follow-up actions: <owner, due date>
```

File every incident write-up regardless of whether the system
self-recovered, per the existing SOP's own closing note.
