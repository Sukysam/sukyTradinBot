# Architecture — SHAP Trade Attribution

Status: **Planned** (Known Gap item 5). Owner:
[04_QUANT_RESEARCHER.md](../04_QUANT_RESEARCHER.md) (build),
[07_SIGNAL_ORCHESTRATOR.md](../07_SIGNAL_ORCHESTRATOR.md) (integrate).
Binding requirements: [Standards/Model Explainability Standard.md](../Standards/Model%20Explainability%20Standard.md).

## Why a target architecture doc exists for something unbuilt

This system's regime detection is generative (Gaussian HMM), which SHAP
does not explain directly — there is no supervised prediction to attribute.
Attribution becomes meaningful once Adaptive Strategy Allocation
(Known Gap item 4) introduces a supervised model in the decision path. This
document specifies the design so the two land coherently, rather than SHAP
being bolted onto whatever allocation model happens to get built first
without an attribution-shaped output in mind.

## Position in the pipeline

```
filtered_probs (HMM)  ─┐
feature_row (technical)─┼──► Adaptive Allocation Model ──► raw model output
sentiment score ────────┤         (core/regime_strategies.py,            │
bandit confidence ──────┘          not yet built)                        │
                                                                          ▼
                                                            core/attribution.py
                                                       shap.TreeExplainer / LinearExplainer
                                                                          │
                                                                          ▼
                                                            AttributionRecord
                                                     {trade_id, feature_names, shap_values,
                                                      base_value, top_contributors}
                                                                          │
                              signal_generator.py appends to the SAME    │
                              trade_context_db.json entry as the         │
                              TradeDecision it explains                 ◄┘
```

## `AttributionRecord` contract (target)

```python
@dataclass(frozen=True)
class AttributionRecord:
    trade_id: str
    model_version: str
    feature_names: tuple[str, ...]
    feature_values: tuple[float, ...]   # frozen at decision time
    shap_values: tuple[float, ...]
    base_value: float
    top_contributors: tuple[tuple[str, float], ...]  # sorted by |shap_value|, descending
```

`feature_values` are captured and frozen at decision time specifically so a
later recomputation from a refreshed feature matrix (which could reflect
restated/corrected historical bars) can never silently produce a
look-ahead-tainted explanation — see
[Standards/Model Explainability Standard.md](../Standards/Model%20Explainability%20Standard.md)
requirement 2.

## Latency handling

SHAP computation (especially `KernelExplainer`, if ever required) can be
slow relative to the 5-minute structural loop's cadence but must never
delay order submission. Target design: compute attribution in a background
task (`asyncio.create_task` fire-and-forget, or a follow-up write) after
`_evaluate_and_submit` has already acted on the `TradeDecision`, and append
the `AttributionRecord` to the trade's `trade_context_db.json` entry
slightly after the fact. The trade context entry's presence does not
depend on attribution completing — a trade must never be blocked or lost
because attribution failed or was slow.

## What attribution is and isn't used for

- **Is**: a debugging and audit tool — reconstructing why an automated
  decision was made, after the fact, for incident review and model-quality
  monitoring (see [Standards/Model Explainability Standard.md](../Standards/Model%20Explainability%20Standard.md)'s
  validation requirements).
- **Is not**: an input to the risk veto layer. `risk_manager.evaluate_trade`
  remains a deterministic function of portfolio/trade state only — SHAP
  values never feed back into whether a trade is approved. Mixing
  explainability into the veto decision would make the one component that
  must be simplest and most auditable in the whole system dependent on the
  most complex.
- **Is not**: a substitute for backtest validation. A stable, sensible-
  looking attribution is necessary but not sufficient evidence a model is
  performing well — see [09_QA_ENGINEER.md](../09_QA_ENGINEER.md)'s
  pitfall note on this exact confusion.

## Build sequencing

Per [02_TECHNICAL_PLANNER.md](../02_TECHNICAL_PLANNER.md)'s build order,
this is explicitly sequenced *after* the Adaptive Strategy Allocation model
has a working, backtested implementation. Building the explainer first
produces a module that explains a placeholder — worthless, and a common
trap when "explainability" gets prioritized as a checkbox rather than
sequenced against what it actually needs to explain.
