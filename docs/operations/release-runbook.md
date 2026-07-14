# Release Runbook

Operationalizes `src/ops`'s WP1–WP4 mechanisms (`ops.health`,
`ops.startup`, `ops.deployment`, `ops.rollback`) into a step-by-step
release procedure. This is the human-facing complement to
[SOPs/Release Workflow.md](../engineering-handbook/SOPs/Release%20Workflow.md)
(which governs the git/PR/tag process) — this document governs what
happens when a built artifact is actually put into a running
environment.

No CI/CD platform executes any of this automatically yet — no
deployment target has been chosen (see
[ADR-025](../engineering-handbook/Architecture/ADR/ADR-025-Deployment-And-Release-Automation-Design.md)).
Every step below is a manual procedure a release owner runs, calling
into the real `ops` functions directly (a Python shell, a script, or a
future CI job once a target exists).

## Preconditions

- The change has passed CI (`ruff`, `black`, `mypy`, full test suite —
  see [SOPs/Release Workflow.md](../engineering-handbook/SOPs/Release%20Workflow.md)).
- A `version` and `git_commit` are known for the build being released.
- Required secrets for the target environment are set (see
  [Configuration & Secrets](../engineering-handbook/Architecture/ADR/ADR-024-Configuration-And-Secrets-Design.md)).

## Procedure

1. **Build a `RuntimeContext` for the target environment.**
   Call `ops.startup.build_runtime_context(version=..., git_commit=..., environment=..., required_secrets=[...])`.
   If this raises `RuntimeValidationError`, stop — the environment or a
   required secret is missing. Do not proceed with a release into an
   environment that can't validate its own configuration.

2. **Build the `ReleaseManifest` and verify artifacts.**
   Compute each artifact's checksum with `ops.deployment.compute_checksum`
   at build time, record it in a `ReleaseManifest`, then re-compute
   checksums for the artifacts actually staged for deployment and call
   `ops.deployment.verify_release_manifest`. If `ValidationResult.valid`
   is `False`, stop — an artifact was corrupted or substituted between
   build and release. Do not deploy anything that fails this check.

3. **Build a `DeploymentInfo` and validate it against the `RuntimeContext`.**
   Construct `DeploymentInfo(version=..., git_commit=..., deployment_environment=...,
   deployment_id=...)` and call `ops.deployment.validate_deployment(runtime, deployment)`.
   If invalid, stop — the deployment describes a different build than
   what's actually running/validated.

4. **Record the current deployment as the rollback target.**
   Before replacing the running process, note the current
   `DeploymentInfo.deployment_id` (or fetch it from deployment history)
   as this new deployment's `rollback_target`. A deployment made without
   a known rollback target is a deployment that can't be undone quickly
   — see [Disaster Recovery](disaster-recovery.md).

5. **Deploy.**
   However the process is actually started/restarted for the chosen
   environment (out of scope for `ops` — see ADR-025 for why no
   specific mechanism is prescribed here yet).

6. **Post-deploy health check.**
   Once the new process is running, evaluate `ops.health.evaluate_health`
   against real subsystem checks and call `ops.health.require_healthy`.
   If it raises `UnhealthyPlatformError`, this is a failed release — go
   straight to the rollback procedure below, do not attempt to
   "wait and see."

7. **Build and archive a `DiagnosticReport`.**
   Call `ops.diagnostics.build_diagnostic_report(runtime, health, deployment=deployment_info)`
   and keep the rendered `ops.reporting.generate_diagnostic_report(report)`
   output with the release record. This is the artifact a future
   incident investigation reads first.

## Rollback procedure

1. Fetch deployment history (every prior `DeploymentInfo` for this
   environment) and call `ops.rollback.select_rollback_target(history, current=deployment)`.
2. Call `ops.rollback.require_rollback_target(target)` — if it raises
   `NoRollbackTargetError`, there is nothing to roll back to; escalate
   per [On-Call Guide](on-call-guide.md) rather than attempting a
   partial or manual rollback.
3. Re-run steps 1–3 above (`build_runtime_context`, artifact
   verification, `validate_deployment`) treating the rollback target's
   `version`/`git_commit` as the build being deployed.
4. Deploy the rollback target the same way step 5 above deploys any
   release.
5. Re-run the post-deploy health check (step 6). A rollback that
   doesn't restore a `HEALTHY` `PlatformHealth` is itself an incident —
   see [Incident Response](incident-response.md).

## Why no automation exists yet

Every step above is manual because no deployment target has been
chosen for this platform (see ADR-025's Alternatives Considered). This
runbook exists so the manual process is consistent and auditable in
the meantime, and so that whichever CI/CD platform is eventually
adopted has an exact, already-tested sequence of `ops` function calls
to wrap in automation — the mechanism doesn't change, only who (or
what) invokes it.
