# Production Readiness Checklist

Run through this before promoting any deployment to a live-trading
environment (as distinct from paper trading or a synthetic-data
backtest). This checklist synthesizes what Milestones 1–12 already
built into one pre-go-live gate; it does not introduce new
requirements beyond what those milestones already established.

## 1. Known Gaps closed

- [ ] Every item in [Architecture/Known Gaps.md](../engineering-handbook/Architecture/Known%20Gaps.md)
      that blocks live operation is closed. Check the file directly —
      it is the live source of truth, not this checklist. Per
      [SOPs/Release Workflow.md](../engineering-handbook/SOPs/Release%20Workflow.md),
      an unclosed blocking gap reaching production is itself a
      release-process failure (see
      [Incident Response](incident-response.md) class 6 in the legacy
      SOP).

## 2. Runtime validates cleanly

- [ ] `ops.startup.build_runtime_context` succeeds for the target
      environment with every secret the deployment actually needs
      listed in `required_secrets` — not just the secrets known to be
      set today, but every one the running process will try to
      resolve.
- [ ] `ops.health.evaluate_health`, run against real subsystem checks
      (not the injected fakes used in tests), returns `HEALTHY` —
      every one of the ten WP1 checks (`configuration`, `market_data`,
      `model_artifact`, `feature_registry`, `hmm_model`,
      `strategy_registry`, `risk_service`, `execution_adapter`,
      `memory_store`, `nlp_pipeline`) passing against the real target
      environment, not a fake probe.

## 3. Deployment tracking is real

- [ ] A `DeploymentInfo` is being constructed for this deployment and
      `ops.deployment.validate_deployment` confirms it matches the
      validated `RuntimeContext`.
- [ ] `ops.rollback.select_rollback_target` returns a real prior
      deployment for this environment — going live for the first time
      in a new environment with no rollback target is a known,
      accepted gap (see [Release Runbook](release-runbook.md)), not
      something to silently ignore; if there truly is no prior
      deployment, this must be a documented, explicit decision, not an
      oversight discovered during an incident.

## 4. Explainability and risk invariants intact

Per [00_MASTER_CHARTER.md](../engineering-handbook/00_MASTER_CHARTER.md):

- [ ] "The risk veto is the only gate on order submission" (invariant
      #2) — confirm nothing bypasses `risk.RiskService` between
      strategy decision and order submission.
- [ ] "Every strategy is long-only" (invariant #5) — confirm no
      strategy or signal-orchestration policy has been reconfigured to
      permit short positions.
- [ ] "Every automated trade decision must be explainable and logged
      before it is actionable" (invariant #6) — confirm
      `StrategyDecision.reasoning`/`ExecutionDecision.reasoning`/
      `OrderIntent`'s rationale chain is populated end to end, not
      defaulted to an empty or placeholder string anywhere in the path
      about to go live.
- [ ] Any new configuration defaults to the safer option (invariant
      #7/#8 language) — spot-check that nothing introduced since the
      last production release silently defaults to "live trading" or
      "no risk limit" when unset.

## 5. Backup and recovery are real, not theoretical

- [ ] The state listed in [Backup & Restore](backup-restore.md) is
      actually being backed up for this environment on a real
      schedule — not just documented as *should* be backed up.
- [ ] A restore has been tested (per [Backup & Restore](backup-restore.md)'s
      verification steps) against this environment's actual backup
      mechanism at least once, not only against a local/synthetic copy.

## 6. On-call is staffed and briefed

- [ ] Whoever is on-call for this deployment has read
      [On-Call Guide](on-call-guide.md) and knows where
      `ops.diagnostics.build_diagnostic_report` output will come from
      for this specific environment (a monitoring loop, a manual
      check, a paging integration — whichever applies).
- [ ] The escalation contacts in [On-Call Guide](on-call-guide.md) are
      current people, not placeholder role names.

## 7. Shadow-mode components remain shadow-mode unless explicitly re-authorized

- [ ] `LearningDecision` (Milestone 9) is not influencing production
      allocation unless a separate, explicit, later decision authorized
      it — confirm `strategy`/`risk`/`execution` still take no new
      dependency on `memory`.
- [ ] `NewsSignal` (Milestone 10) is similarly still shadow-mode unless
      explicitly authorized.
- [ ] `FinalDecision` (Milestone 11) is still not wired to replace
      `StrategyDecision` as `risk.RiskService`'s input unless explicitly
      authorized — see
      [ADR-020](../engineering-handbook/Architecture/ADR/ADR-020-FinalDecision-Contract.md)'s
      "Wiring is not yet authorized" section.

## Sign-off

Do not check this box until every section above is checked:

- [ ] **Explicit sign-off recorded** from whoever owns the go-live
      decision, referencing this checklist by date and commit.
