# Backup & Restore

What must be backed up, what doesn't need to be, and how to verify a
restore actually worked. Referenced by
[Disaster Recovery](disaster-recovery.md); this document owns the
specifics of *what*, that one owns *when to use it*.

## Must be backed up

| State | Location | Why |
|---|---|---|
| `risk_manager.EMERGENCY_HALT.lock` | process working directory (legacy `regime-trader/core/risk_manager.py`, `DEFAULT_EMERGENCY_LOCK_PATH`) | Only a human clears it (per [SOPs/Incident Response Runbook.md](../engineering-handbook/SOPs/Incident%20Response%20Runbook.md) class 3). Its presence or absence must survive a disaster exactly as it was — see [Disaster Recovery](disaster-recovery.md) step 1. |
| HMM model artifacts: `model.pkl`, `normalizer.pkl`, `metadata.json` | `{base_dir}/{symbol}/{model_version}/` (see [ADR-007](../engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md)) | Without these, `hmm_model_check` (WP1) fails and `RegimeService` cannot produce a `RegimeState` — the platform cannot reach `HEALTHY`. |
| `JsonlExperienceStore` file | wherever `memory.store.JsonlExperienceStore` is configured to append | Append-only adaptive-learning history (Milestone 9). Losing it resets `MemoryService`'s bandit posteriors to their prior, not a trading-safety issue but a real loss of learned state. |
| `JsonlNewsItemStore` file | wherever `nlp.store.JsonlNewsItemStore` is configured to append | Append-only news ingestion history (Milestone 10) — dedup state and sentiment-attribution history. |
| Deployment history (sequence of `DeploymentInfo` records) | wherever the release process persists it (not yet specified — see [ADR-025](../engineering-handbook/Architecture/ADR/ADR-025-Deployment-And-Release-Automation-Design.md)) | Without it, `ops.rollback.select_rollback_target` has nothing to select from. |
| `config/feature_manifest.yaml` and any environment-specific `config/*.yaml` | `config/` | Non-secret structured configuration (`common.config.load_yaml_config`) — needed to reconstruct the exact feature pipeline a model was trained against. |

## Must NOT be backed up as plaintext

- **Secret values** (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, or anything
  resolved through `ops.secrets.SecretSource`) — never write these to
  a backup archive. Restoring secrets is a re-provisioning step through
  the same `SecretSource` mechanism used in normal operation (see
  [Disaster Recovery](disaster-recovery.md) step 3), not a
  backup-restore step. A backup containing plaintext secrets is a
  second, uncontrolled copy of exactly the material
  `ops.secrets.SecretValue`'s redacted `repr`/`str` exists to keep out
  of logs and error messages — don't undo that by putting it in a
  backup archive instead.

## Does not need to be backed up (regenerable)

- Exported metrics (`ops.metrics.MetricsRegistry` state) — in-memory,
  reset on process restart by design; nothing to restore.
- Structured logs — valuable for investigation but not required for
  the platform to resume operating; retain per whatever log-aggregation
  retention policy is in place, not as part of this backup set.
- `PlatformHealth`/`DiagnosticReport` snapshots — always recomputable
  from current state via `ops.health.evaluate_health`/
  `ops.diagnostics.build_diagnostic_report`; archiving a specific past
  report (e.g. from an incident) is useful for the incident record, not
  a backup requirement.

## Restore verification

A restore is not complete until verified — do not assume a copied file
is a working file:

1. Restore the files listed above to their expected paths.
2. Run the full startup sequence
   (`ops.startup.build_runtime_context`, per
   [Release Runbook](release-runbook.md)) against the restored state.
3. Run `ops.health.evaluate_health` with real subsystem checks and
   confirm `status` is `HEALTHY` — specifically confirm `hmm_model_check`
   and `memory_store_check` pass, since those two depend directly on
   the restored HMM artifacts and experience store.
4. If `JsonlExperienceStore`/`JsonlNewsItemStore` were restored,
   confirm `JsonlExperienceStore.load(path)`/`JsonlNewsItemStore.load(path)`
   replay without raising — both stores validate every line against
   their record type at load time and raise on the first corrupt line
   (see `memory.store`/`nlp.store`), so a successful load is itself a
   meaningful integrity check.
5. Only after all of the above pass, consider the restore verified and
   proceed with the rest of [Disaster Recovery](disaster-recovery.md).
