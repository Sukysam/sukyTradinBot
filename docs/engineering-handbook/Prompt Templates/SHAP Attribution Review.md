# Template — SHAP Attribution Review

Use when reviewing a batch of `AttributionRecord`s (e.g. weekly review of
the Adaptive Strategy Allocation model's decisions, or investigating a
specific losing trade). Applies once
[core/attribution.py](../Architecture/SHAP%20Trade%20Attribution.md) exists.

```
Review scope: <single trade_id | date range | all trades for a given
strategy/regime>

For each AttributionRecord reviewed:
- trade_id: <id>
- Model version: <model_version>
- Top 3 contributors (feature, shap_value): <...>
- Direction sanity: does each top contributor's sign match domain
  intuition? (e.g. positive RSI-momentum contributing positively to a
  long entry) [ ] yes [ ] no — explain
- Base value vs. final prediction: <base_value> → <predicted output>

Aggregate findings across the reviewed batch:
- Any feature dominating attribution for an unexpectedly large share of
  trades? (per Standards/Model Explainability Standard.md's "no spurious
  dominance" requirement) [ ] no concern [ ] flagged — describe
- Any systematic direction mismatch for a given feature across multiple
  trades (vs. isolated noise)? [ ] no [ ] yes — describe
- Does attribution pattern differ meaningfully across regimes in a way
  that makes sense given each regime's definition? [ ] yes, sensible
  [ ] unclear — needs Quant Researcher input

Action items:
- [ ] No action — attribution consistent with expected model behavior
- [ ] Flag to Quant Researcher (04_QUANT_RESEARCHER.md) — possible
      spurious feature reliance
- [ ] Flag to Signal Orchestrator (07_SIGNAL_ORCHESTRATOR.md) — possible
      allocation logic issue
- [ ] File incident per SOPs/Incident Response Runbook.md if a live
      trading decision was materially explained by an implausible feature
```

Read [Standards/Model Explainability Standard.md](../Standards/Model%20Explainability%20Standard.md)'s
validation requirements before starting a review — they define what
"sanity," "stability," and "no spurious dominance" mean precisely.
