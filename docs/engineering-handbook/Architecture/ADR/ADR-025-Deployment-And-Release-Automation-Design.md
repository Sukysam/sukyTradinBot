# ADR-025: Deployment & Release Automation Design

**Status**: Accepted
**Date**: 2026-07-14
**Milestone**: [12 (WP4) — Deployment & Release Automation](../../../../PROJECT_STATUS.md)

## Context

WP1–WP3 built health reporting, observability, and runtime
validation/secrets, each reading or composing the prior work package's
operational model rather than duplicating it. WP4 is scoped around the
product owner's proposed pipeline:

```
ValidatedRuntime -> Deployment Validator -> Release Package -> Deployment -> Rollback
```

with explicit instruction to "keep WP4 focused on deployment mechanics
rather than runtime behavior," extend `src/ops/` "only where runtime
code is actually needed," and keep "deployment-specific assets
(workflows, manifests, scripts) outside `src/` where appropriate." The
product owner also proposed a new immutable model, `DeploymentInfo
{version, git_commit, build_time, deployment_environment,
deployment_id, rollback_target}`, explicitly distinct from
`PlatformInfo`: "`PlatformInfo` describes the software build.
`DeploymentInfo` describes a particular deployment instance."

Before starting, the current state of deployment-adjacent tooling in
this repository was checked: a `Dockerfile` and `docker-compose.yml`
exist (Milestone 1 — they build and run a container), and
`.github/workflows/ci.yml` runs lint/type/test/build on every PR. No
Kubernetes manifest, no Terraform, no release/rollback script, and no
"deploy to X" CI job exist anywhere in this repository. No deployment
target (a specific hosting platform, orchestrator, or environment) has
been chosen.

## Decision

### 1. `DeploymentInfo`, exactly as proposed

`ops.models.DeploymentInfo` is added with the proposed shape and
distinction intact: the same build (`version`/`git_commit`) can be
deployed more than once, to more than one `deployment_environment`,
each a separate `DeploymentInfo` with its own `deployment_id`.
`rollback_target` is `str | None`, naming the `deployment_id` this
deployment would roll back to if needed.

### 2. `ops.deployment`: validation and artifact verification, not orchestration

`validate_deployment(runtime, deployment)` checks that a
`DeploymentInfo` actually describes the `RuntimeContext` it's paired
with (`version`/`git_commit` must match) — implementing the
"Deployment Validator" step directly. `ReleaseManifest` +
`verify_release_manifest` implement "Release Package" + artifact
verification: a manifest records the expected SHA-256 checksum of every
artifact in a release; `verify_release_manifest` compares those against
actual checksums (`compute_checksum`, a thin `hashlib.sha256` wrapper)
and reports every mismatch, not just the first. Both functions return
`ops.validation.ValidationResult` — the same report shape `validate_runtime`
already uses, rather than inventing a second one; `require_valid_deployment`
mirrors `require_valid_runtime` exactly.

### 3. `ops.rollback`: a separate module because it operates on history, not one object

Every function in `ops.deployment` takes a single `DeploymentInfo` (or
`ReleaseManifest`). `select_rollback_target` takes a *sequence* of
prior deployments and picks the most recent one that isn't the current
deployment — a structurally different input shape, the same reasoning
that already separated `orchestration.evaluation` (paired history) from
`orchestration.arbitration` (single decision) in Milestone 11.
`require_rollback_target` is the fail-fast gate, raising
`NoRollbackTargetError` when a rollback has nothing to roll back to —
a rollback that silently no-ops when there's no target would be exactly
the failure mode this handbook's invariants exist to prevent.

### 4. Deliberately deferred: deployment manifests, release automation scripts, CI "deploy" workflow

Two of the six responsibilities listed for WP4 — "deployment manifests"
and "release automation" — are **not** implemented in this work
package. No Kubernetes YAML, no Terraform, no shell script, and no new
GitHub Actions job were added. This is a scope decision, made for the
same reason ADR-023 deferred a real tracing-SDK integration and
ADR-024 deferred a real secrets-manager client: **no deployment target
has been chosen**. A Kubernetes manifest without a cluster to apply it
to, or a "deploy" workflow without a hosting platform to deploy to,
would be speculative infrastructure — exactly what this handbook's
"build the mechanism, defer the target-specific wiring until a target
is chosen" pattern has consistently avoided since Milestone 9 (memory
loop shadow mode), Milestone 10 (NLP shadow mode), and every "wiring
not yet authorized" note since. What *is* built — `DeploymentInfo`,
deployment validation, artifact-checksum verification, and rollback
target selection — is the mechanism a real manifest/script/workflow
would call into, once a target exists to write one for. This is the
literal instruction to extend `src/ops/` "only where runtime code is
actually needed" applied to its logical conclusion: no target-specific
runtime code exists to write yet.

## Consequences

- WP4 gives a future deployment automation script (bash, a GitHub
  Actions job, whatever platform is eventually chosen) four call
  points: build a `DeploymentInfo`, call `validate_deployment` against
  the current `RuntimeContext`, call `verify_release_manifest` against
  the artifacts about to ship, and — on failure — call
  `select_rollback_target` against deployment history. None of that
  logic needs to be rewritten once a target is chosen; only the
  wrapper script that calls it does.
- `src/ops` remains pure stdlib after WP4 — `compute_checksum` uses
  only `hashlib`/`pathlib`.
- Trade-off, accepted: this work package produces no artifact a
  DevOps engineer could point a real CI/CD pipeline at today. That is
  the deliberate consequence of §4, not an oversight — see Alternatives
  Considered for what was rejected instead.
- `DeploymentInfo`/`ReleaseManifest`/rollback selection are not yet
  wired into anything upstream (`ops.health`, `ops.metrics`, `ops.logging`,
  `ops.alerts` don't reference `DeploymentInfo`) — a later work package
  (WP5, or a revisit of WP2) could log/alert on a rollback event once a
  real trigger exists to produce one.

## Alternatives Considered

- **Write a Kubernetes Deployment/Service manifest** — rejected: no
  container orchestrator has been chosen for this platform; a manifest
  for a cluster that doesn't exist would be unverifiable and likely
  wrong by the time a real one is provisioned.
- **Write a GitHub Actions "deploy" job** — rejected for the same
  reason: deploy *to where*? `ci.yml` today runs lint/type/test/build
  only; adding a deploy step requires a real target's credentials and
  API, neither of which exist.
- **Write a shell-script release/rollback tool** — rejected: without a
  chosen artifact registry, hosting platform, or process-supervision
  mechanism to script against, a "release script" would just be
  `ops.deployment`'s Python functions re-expressed less testably in
  bash, for no real capability gained.
- **Skip `ops.rollback` as a separate module, fold `select_rollback_target`
  into `ops.deployment`** — rejected: see Decision §3. A function
  operating over a sequence of prior deployments is a different shape
  of concern from single-object validation, the same distinction that
  already justified separate modules elsewhere in `ops` (`ops.checks`
  vs. `ops.health`) and `orchestration` (`arbitration` vs.
  `evaluation`).
- **Give `verify_release_manifest`/`validate_deployment` their own
  bespoke result type instead of reusing `ops.validation.ValidationResult`**
  — rejected: both are structurally identical to what `validate_runtime`
  already returns (a boolean plus a tuple of error strings); a second,
  differently-named type with the same shape would just be one more
  thing a reader has to learn is equivalent to the first.
