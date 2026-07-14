# ADR-026: Operations & Diagnostics Design

**Status**: Accepted
**Date**: 2026-07-14
**Milestone**: [12 (WP5) — Operations & Runbooks](../../../../PROJECT_STATUS.md)

## Context

WP1–WP4 built health reporting, observability, runtime validation, and
deployment/rollback mechanics, all inside `src/ops/`. WP5 is the final
work package of Milestone 12, scoped by explicit instruction to move
*out* of `src/`: "Most of WP5 should be documentation and operational
assets rather than runtime Python," specifically six documents under
`docs/operations/` (release runbook, incident response, disaster
recovery, backup/restore, on-call guide, production checklist), plus
one small runtime addition if it "genuinely supports operational
workflows": a `DiagnosticReport` composing `PlatformInfo`,
`RuntimeContext`, `DeploymentInfo`, and `PlatformHealth` into one
snapshot, produced by a new `ops.diagnostics` module.

This record covers both: the `DiagnosticReport` design, and how the
six `docs/operations/` documents relate to documentation that already
existed before Milestone 12 (`docs/engineering-handbook/SOPs/Incident
Response Runbook.md` and `SOPs/Release Workflow.md`).

## Decision

### 1. `DiagnosticReport` composes, never duplicates

`ops.models.DiagnosticReport{runtime_context, health, deployment_info,
generated_at}` holds no field that already lives on one of its
components. `version`/`git_commit`/`environment` are read via
`runtime_context.platform_info`/`runtime_context.environment` — adding
second copies would reintroduce exactly the duplicated-source-of-truth
risk `RuntimeContext` (ADR-024) and `DeploymentInfo` (ADR-025) were
each designed to avoid relative to `PlatformInfo`. `deployment_info` is
`Optional[DeploymentInfo]`, not required — a `DiagnosticReport` must
stay constructible in an environment that has no deployment tracking
wired up yet (every environment this platform has today, per ADR-025's
own deferral).

`ops.diagnostics.build_diagnostic_report` is orchestration only, the
same role `ops.startup.build_runtime_context` plays one layer down: it
takes an already-computed `RuntimeContext` and `PlatformHealth` as
inputs rather than recomputing either, so a `DiagnosticReport` can
never disagree with the objects it's built from by construction, not
by convention. `ops.reporting.generate_diagnostic_report` renders it as
text, alongside the existing `generate_health_report`, following that
module's own "consumes the model, never shapes it" convention.

### 2. `docs/operations/` complements the existing handbook, doesn't replace it

Two documents already existed before Milestone 12:
`SOPs/Incident Response Runbook.md` (trading-domain incidents: circuit
breaker halts, emergency hard stop, liquidation failure — ported from
`regime-trader/core/risk_manager.py`) and `SOPs/Release Workflow.md`
(the git/PR/tag process). Rather than duplicating either,
`docs/operations/incident-response.md` explicitly complements the
existing SOP (new `src/ops`-detectable incident classes only — startup
validation failure, platform unhealthy/degraded, deployment drift,
checksum mismatch, no-rollback-target), and
`docs/operations/release-runbook.md` explicitly complements the
existing Release Workflow (this one governs what happens once a build
is actually put into a running environment, calling directly into the
real `ops.startup`/`ops.deployment`/`ops.rollback`/`ops.health`
functions built across WP1–WP4). Every `docs/operations/` document
cross-links back to the relevant handbook document and to each other,
rather than repeating shared content (the incident write-up template,
the escalation role docs, the Known Gaps reference) in more than one
place.

### 3. No new runtime automation beyond `DiagnosticReport`

Every procedure in `docs/operations/` is written as a manual sequence
of calls into already-built `ops` functions, consistent with
ADR-025's "no deployment target chosen yet" scope. No new Python
module executes a runbook automatically; `ops.diagnostics` is the one
runtime addition, because a diagnostic snapshot is genuinely useful
independent of what triggers reading it (a human running it by hand
today, a monitoring loop calling it automatically once one exists), the
same reasoning that justified `ops.health.evaluate_health` existing
before any real subsystem probe was wired to it.

## Consequences

- Milestone 12 is now feature-complete across all five work packages:
  WP1 (health), WP2 (observability), WP3 (configuration & secrets),
  WP4 (deployment & release automation), WP5 (operations &
  diagnostics). Per the product owner's stated intent, this marks the
  point where Milestone 12 as a whole can be considered complete and a
  final umbrella release considered — a separate, explicit decision
  from this ADR.
- Every `docs/operations/` procedure names the exact `ops` function it
  calls at each step, so once a real deployment target and monitoring
  loop exist, automating any of these runbooks is a matter of scripting
  the already-documented sequence, not re-deriving it.
- `DiagnosticReport` gives every future operational surface (a status
  page, an automated page-triage step, a support tool) one function to
  call for "what do we currently know about this process," rather than
  each reinventing its own combination of `RuntimeContext`/
  `PlatformHealth`/`DeploymentInfo`.
- Trade-off, accepted: the `docs/operations/` documents describe
  procedures for infrastructure (backup scheduling, paging
  integrations, a real deployment target) that doesn't exist yet. They
  are written to be correct and specific about what `ops` can do today,
  and explicit about what remains manual or undecided — not aspirational
  descriptions of infrastructure this platform doesn't have.

## Alternatives Considered

- **Flatten `DiagnosticReport`'s fields (duplicate `version`,
  `git_commit`, `environment` directly on it)** — rejected: see
  Decision §1. Would reintroduce the exact duplicated-source-of-truth
  risk `RuntimeContext`/`DeploymentInfo` were each designed to avoid.
- **Make `deployment_info` required** — rejected: no environment this
  platform runs in today has deployment tracking wired up (ADR-025);
  requiring it would make `DiagnosticReport` unconstructable in every
  environment that currently exists.
- **Rewrite `SOPs/Incident Response Runbook.md` and `SOPs/Release
  Workflow.md` in place instead of adding new, cross-linked documents**
  — rejected: both existing documents remain accurate for what they
  already cover (trading-domain incidents, the git/PR/tag process); the
  new Milestone 12 material is additive, not a correction to either,
  and keeping them separate avoids one document trying to serve two
  different audiences (trading-domain on-call vs. platform-operations
  on-call) at once.
- **Write `docs/operations/` procedures as executable scripts instead
  of documents** — rejected for this work package: no deployment target
  or monitoring loop exists yet to run a script against (same reasoning
  ADR-025 already gave for deferring release automation specifically);
  a document that names the exact function to call at each step is the
  more honest artifact until a real target exists to script against.
