# Disaster Recovery

Covers loss scenarios beyond a single failed release or a routine
health-check failure (both covered by
[Incident Response](incident-response.md) and
[Release Runbook](release-runbook.md)): loss of the host the platform
runs on, corruption of on-disk state, or a bad deployment that
`ops.rollback` alone can't recover from because the state it's
rolling back to no longer exists.

## What "disaster" means for this platform

This platform is a single-process trading system with local,
file-based state (no external database, no managed persistence layer —
see [Architecture/Known Gaps.md](../engineering-handbook/Architecture/Known%20Gaps.md)
for what's deliberately not built yet). A disaster here is any event
that destroys or corrupts that local state:

- Host loss (disk failure, instance termination, filesystem corruption).
- Corrupted or truncated state files (a crash mid-write to a JSONL
  store, a partial `model.pkl` write).
- A bad deployment whose rollback target (per
  [Release Runbook](release-runbook.md)) also turns out to be
  compromised or missing.

## What must survive a disaster

See [Backup & Restore](backup-restore.md) for exactly what to back up
and how often. In recovery-priority order:

1. **`risk_manager.EMERGENCY_HALT.lock`** (if present) — the one piece
   of state that must never be silently lost or silently recreated. Its
   absence after a disaster must be treated as "unknown prior state,"
   not as "no halt was active." See step 1 below.
2. **HMM model artifacts** (`model.pkl`, `normalizer.pkl`,
   `metadata.json` per symbol/version — see
   [ADR-007](../engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md)) —
   without these, `hmm_model_check` (WP1) fails and the platform cannot
   reach `HEALTHY`.
3. **`JsonlExperienceStore`/`JsonlNewsItemStore`** append-only logs
   (Milestones 9/10) — losing these loses adaptive-learning and
   sentiment-attribution history, not current trading capability; lower
   priority than 1–2 but should still be restored before those
   subsystems are relied on again.
4. **Deployment history** (the sequence of `DeploymentInfo` records
   `ops.rollback.select_rollback_target` reads) — without it, a
   rollback after the disaster has no target to select.

## Recovery procedure

1. **Before restarting anything, determine whether
   `risk_manager.EMERGENCY_HALT.lock` existed before the disaster.**
   Check the most recent backup (see
   [Backup & Restore](backup-restore.md)). If it's ambiguous whether an
   emergency halt was active, treat the platform as halted until a
   human confirms otherwise — per
   [SOPs/Incident Response Runbook.md](../engineering-handbook/SOPs/Incident%20Response%20Runbook.md)
   class 3, this lock is the one piece of state only a human clears,
   and "we're not sure" must resolve to the safer state (halted), per
   [00_MASTER_CHARTER.md](../engineering-handbook/00_MASTER_CHARTER.md)'s
   "any new configuration defaults to the safer option" invariant.
2. **Restore state from the most recent verified backup** — model
   artifacts, experience/news stores, deployment history.
3. **Provision a new host** (or repair the existing one) and restore
   the `.env`/secret configuration for the target environment (never
   from a backup of secret *values* — see
   [Backup & Restore](backup-restore.md)'s explicit exclusion; re-issue
   or re-fetch secrets through the same `SecretSource` mechanism used
   in normal operation).
4. **Run the full release procedure** ([Release Runbook](release-runbook.md))
   from step 1 (`build_runtime_context`) — a disaster recovery is a
   deployment like any other, and skipping validation because "we're in
   a hurry" is exactly the failure mode `RuntimeValidationError` exists
   to prevent.
5. **Confirm `PlatformHealth` is `HEALTHY`** before considering trading
   capability restored. A recovery that leaves the platform `DEGRADED`
   is not a completed recovery.
6. **File a full post-mortem** regardless of root cause, per
   [Incident Response](incident-response.md)'s write-up template — a
   disaster is always incident-worthy.

## What this document does not cover

Multi-region failover, active-active redundancy, and automated backup
scheduling are all deliberately out of scope — this platform has one
deployment target concept, not a distributed one, and no such
infrastructure has been chosen (same reasoning as
[ADR-025](../engineering-handbook/Architecture/ADR/ADR-025-Deployment-And-Release-Automation-Design.md)'s
deferral of CI/CD platform integration). This document describes
recovery for the single-host deployment model this platform actually
has today.
