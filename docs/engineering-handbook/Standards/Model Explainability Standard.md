# Standard — Model Explainability (SHAP Trade Attribution)

Governs the design, validation, and use of the planned SHAP-based trade
attribution capability. See
[Architecture/SHAP Trade Attribution.md](../Architecture/SHAP%20Trade%20Attribution.md)
for the architecture diagram; this document is the binding standard for
anyone implementing or consuming it.

## Why this exists

A production system that automatically allocates capital needs a defensible
answer to "why did it do that" for every trade — for debugging, for
detecting spurious correlations before they cause losses, and for audit
and regulatory defensibility. SHAP (SHapley Additive exPlanations) gives a
theoretically grounded, per-prediction feature attribution for the
Adaptive Strategy Allocation model once it exists.

## Scope

Applies to `core/attribution.py` (not yet built) and its integration point
in `core/signal_generator.py`. Does **not** apply to:

- The HMM regime engine directly — it's generative, not a supervised
  scorer, so SHAP doesn't apply to it directly. Its *outputs*
  (`filtered_probs`) are legitimate SHAP *inputs* once they feed the
  allocation model.
- The risk veto layer (`risk_manager.py`) — it's a deterministic rule
  engine with human-readable rejection reasons already; it needs no
  statistical explainability layer.
- FinBERT sentiment scoring — its output (a probability distribution over
  3 classes) is already directly interpretable; SHAP attribution over
  attention weights is out of scope unless a specific need arises.

## Requirements for implementation

1. **Explainer choice matches model type.** `shap.TreeExplainer` for
   gradient-boosted models, `shap.LinearExplainer` for linear/logistic
   models. `shap.KernelExplainer` (model-agnostic but expensive) only if
   neither applies, and only after a latency budget review with
   [System Architect](../01_SYSTEM_ARCHITECT.md).
2. **No look-ahead in attribution.** Attribution is computed only over the
   exact feature vector the model saw at decision time — captured and
   frozen at decision time, never recomputed later from a refreshed
   feature matrix (which could reflect restated/corrected bars).
3. **Background dataset hygiene.** The explainer's background/reference
   dataset is re-validated whenever the underlying model or the HMM
   feeding it is refit — an attribution computed against a stale
   background distribution can be misleading even if the model itself is
   current.
4. **Non-blocking latency.** SHAP computation must not delay order
   submission. Profile it; if not comfortably sub-100ms, compute and
   attach the attribution record slightly after order submission rather
   than gating execution on the explanation.
5. **One record per trade, attached to the existing store.** Output is an
   `AttributionRecord` (frozen dataclass: `trade_id`, `feature_names`,
   `shap_values`, `base_value`, `top_contributors`) appended to the
   existing `trade_context_db.json` entry for that trade — never a
   separate file or store to keep in sync.

## Validation requirements before production use

- **Stability**: identical inputs produce identical SHAP values across
  repeated runs (deterministic explainer, fixed seed where applicable).
- **Sanity**: attribution direction matches domain intuition for at least
  the top-3 most consistently influential features (e.g. a strongly
  positive RSI-momentum feature attributing positively to a long entry) —
  a persistent sign mismatch is a modeling bug, not a quirky explanation.
- **No spurious dominance**: no single feature should dominate attribution
  for a majority of trades unless there's a clear domain reason (e.g. a
  catalyst-strategy trade dominated by the sentiment feature is expected;
  an unrelated feature like raw volume dominating most trades warrants
  investigation).
- **Coverage**: every `TradeDecision` produced by the allocation model has
  a corresponding `AttributionRecord` — verified by a test, not spot
  checks, per [09_QA_ENGINEER.md](../09_QA_ENGINEER.md).

## Using attribution in review and incident response

- When reviewing a losing trade, pull its `AttributionRecord` first —
  compare the top contributing features against what the human reviewer
  would expect, and treat a mismatch as a signal-quality lead, not just
  trivia.
- When a circuit breaker fires, [Risk Manager](../08_RISK_MANAGER.md) may
  consult recent attribution records during incident review (per its
  charter) to understand what the allocation model was responding to, but
  attribution is never an input to the veto decision itself — the veto
  layer stays a deterministic function of portfolio/trade state only.
- Model cards (owned by
  [Documentation Engineer](../11_DOCUMENTATION_ENGINEER.md)) summarize
  aggregate attribution patterns (typical top features by regime) as part
  of each model version's documentation.

## Ownership

Build: [Quant Researcher](../04_QUANT_RESEARCHER.md). Integration:
[Signal Orchestrator](../07_SIGNAL_ORCHESTRATOR.md). Validation:
[QA Engineer](../09_QA_ENGINEER.md). Audit trail presentation:
[Documentation Engineer](../11_DOCUMENTATION_ENGINEER.md).
