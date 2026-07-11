# Template — Model Drift Investigation

Use when investigating whether a deployed model (HMM regime engine, the
Adaptive Strategy Allocation model, or the RL memory loop's bandit
posteriors) has drifted from the distribution it was fit/calibrated on.

```
Model under investigation: <HMM per-ticker | allocation model | bandit arm(s)>
Trigger for this investigation: <scheduled review | anomalous live
behavior | SHAP Attribution Review flag | post-incident root cause>

## Evidence gathering

1. Recent live inputs vs. training/fit distribution:
   - Compare recent feature_row *_z values against the distribution seen
     during the model's original fit window. Large, sustained shifts in
     mean/variance for any feature are the primary drift signal.
   - For the HMM specifically: compare recent filtered_probs entropy
     against historical — a model that's become persistently uncertain
     (high entropy, no state dominates) may indicate the fitted regimes no
     longer describe current market structure.
   - For the bandit: check whether recently-active arms have accumulated
     enough n_observations to be statistically meaningful, or whether
     drift is really just sparse-data noise in an under-observed arm.

2. Performance comparison:
   - Backtest the currently-deployed model against a recent held-out
     window and compare against its original validation-window
     performance (Quant Researcher's acceptance criteria numbers).
   - A material, sustained gap between original and recent performance is
     the strongest evidence of real drift (vs. one-off market noise).

3. Attribution comparison (once SHAP is built):
   - Compare recent AttributionRecord top-contributor patterns against
     historical baseline patterns for the same regime/strategy — a shift
     in which features dominate is itself informative even independent of
     raw performance numbers.

## Conclusion

- [ ] No drift — variance within expected historical range
- [ ] Drift detected, low severity — monitor, no action yet
- [ ] Drift detected, action required — route to Quant Researcher
      (04_QUANT_RESEARCHER.md) for HMM/allocation model, or Memory
      Engineer (05_MEMORY_ENGINEER.md) for bandit-arm concerns

If action required, follow
SOPs/Model Retraining and Online Learning.md for the applicable
retraining/reset procedure — never hand-edit model parameters or
posteriors directly in response to a drift finding.
```
