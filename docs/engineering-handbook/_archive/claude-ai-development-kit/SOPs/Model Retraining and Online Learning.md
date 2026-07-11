# SOP — Model Retraining & Online Learning

Governs both mechanisms this system uses to adapt over time: the
**implemented** weekly bandit posterior update (RL memory loop /
online learning), and the **planned** HMM refresh cadence. Two different
risk profiles, two different procedures — do not run them under the same
checklist.

## A. Weekly bandit posterior update (implemented, automatic)

This runs unattended via the weekend cron
(`RegimeTraderApp._weekend_cron_loop` → `LearningEngine.run_weekly_optimization`).
No manual SOP is required for the routine case — that's the point of
online learning. This section covers the exceptions.

### When to intervene manually

- **Missed run.** No weekly optimization log line by Sunday means the
  process was down during Saturday's window (no catch-up logic exists).
  Confirm via logs, then decide whether to manually invoke
  `run_weekly_optimization` with an explicit `as_of` covering the missed
  window, or accept the skip — a skip is safe (idempotent, no data lost,
  just a delayed update), so this is rarely urgent.
- **Suspected posterior corruption.** If `learning_weights.json` looks
  wrong (e.g. an arm with an implausible posterior given known trade
  history), reconstruct it from `trade_context_db.json` via a from-scratch
  replay rather than hand-editing the JSON — hand-editing breaks the
  audit trail between recorded trades and current beliefs.
- **Reset request.** Wholesale reset of `learning_weights.json` (e.g.
  after a strategy overhaul that makes historical arms meaningless) is a
  **named, reviewed procedure**, never an ad hoc file deletion — per
  [00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md) invariant #7. Requires
  sign-off from [Memory Engineer](../05_MEMORY_ENGINEER.md) and
  [Technical Planner](../02_TECHNICAL_PLANNER.md), and a written note in
  the PR/commit explaining why prior learning is being discarded.

### Verification after any manual intervention

1. Run `LearningEngine.run_weekly_optimization` against a temp copy of
   `trade_context_db.json` and diff the resulting arm snapshot against
   what's live.
2. Confirm idempotency: run it twice, confirm the second run updates zero
   arms.
3. Only then apply to the live `learning_weights.json`.

## B. HMM model refresh (planned — Known Gap item 3)

Once the model store exists, this section becomes the binding procedure
for any per-ticker HMM refit. Until then, this documents the required
shape of that procedure so it's designed correctly the first time.

### Pre-refit checklist

1. Confirm sufficient new data has accumulated since the last fit to
   justify a refit (avoid refitting on noise).
2. Pull the refit window per
   [Quant Researcher](../04_QUANT_RESEARCHER.md)'s feature/lookback
   conventions (`FEATURE_HISTORY_LOOKBACK_DAYS`).
3. Run `fit_with_bic_selection` with a logged, explicit `random_state`.
4. Compare the new fit's BIC and component count against the prior model
   — a large, unexplained jump in component count warrants investigation
   before deployment, not automatic acceptance.

### Validation before deployment (see [09_QA_ENGINEER.md](../09_QA_ENGINEER.md))

1. Run the new model's `ForwardFilter` against a recent held-out window
   and compare regime classifications against the currently live model.
2. Flag and investigate any large, unexplained divergence before
   deploying — a refit that reclassifies most of recent history into a
   different regime is either a genuine regime shift (rare, worth a
   human look) or a fitting artifact (common, should not go live).
3. Confirm the new model's `n_components` and covariance structure are
   compatible with everything downstream that consumes `filtered_probs`
   shape (`StabilityFilter`, `SignalGenerator`, the planned allocation
   model).

### Deployment

1. Model artifact is versioned and stored per
   [Architecture/Production Deployment.md](../Architecture/Production%20Deployment.md)'s
   target design.
2. `ForwardFilter.reset()` is called for every affected ticker at the
   swap point — a stale `log_alpha` computed under the old model's
   parameters must never be reused with new model parameters.
3. Rollback plan (revert to the prior model artifact) is confirmed working
   before the new model is treated as the deployed default.

### Must escalate

- Any refit that changes `n_components` for a ticker already in
  production — this changes the shape of `filtered_probs` and may require
  coordinated changes in `regime_strategies.py`'s regime-label mapping.
- Any refit whose validation step (above) shows material disagreement with
  the currently live model on recent history.
