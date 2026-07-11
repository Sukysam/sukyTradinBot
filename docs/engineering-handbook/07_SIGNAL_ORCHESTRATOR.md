# 07 — Signal Orchestrator

## Mandate

Own the module that doesn't exist yet and matters most:
`core/signal_generator.py` (+ `core/regime_strategies.py`) — the component
that turns HMM regime probabilities, feature values, sentiment scores, and
the RL memory loop's confidence weight into an actual `TradeDecision`.
Everything upstream produces signals; everything downstream (risk,
execution) acts on a decision; this role is where signals become a
decision, and — once built — where that decision gets attached to its SHAP
explanation.

## Capability ownership

| Capability | This role's responsibility |
|---|---|
| Adaptive Strategy Allocation | Owns the decision-routing logic (which strategy fires, how the RL confidence weight scales size); the underlying statistical model is built by Quant Researcher |
| SHAP Trade Attribution | Integrates the attribution call into the decision path; the explainer itself is built by Quant Researcher |
| Reinforcement Learning Memory Loop | Sole consumer of `LearningEngine.sample_confidence_weight` at decision time; sole writer of `trade_context_db.json` |

## Owns (once built)

- `core/signal_generator.py` — implements the `SignalGenerator` `Protocol`
  already defined in `main.py`:
  - `evaluate_bar(ticker, filtered_probs, feature_row) -> Optional[TradeDecision]`,
    called after the 3-bar stability filter confirms a regime.
  - `evaluate_catalyst(news, sentiment, filtered_probs) -> Optional[TradeDecision]`,
    called from the event-driven news pipeline.
- `core/regime_strategies.py` — the regime-tier → allocation logic (Spec
  Sec. 3): what counts as `"LOW_VOL"` / `"MID_VOL"` / `"HIGH_VOL"` /
  `"NEUTRAL"`, and what strategy applies in each. Hosts the Adaptive
  Strategy Allocation model designed in
  [Quant Researcher](04_QUANT_RESEARCHER.md)'s target architecture.
- Writing entries to `data/trade_context_db.json` on entry and on position
  closure — the **sole writer** of that file — and, once
  `core/attribution.py` exists, appending its `AttributionRecord` to the
  same entry.

## Core responsibilities & workflows

1. **Decision synthesis.** Combine `filtered_probs`, `feature_row`,
   `SentimentScore` (when catalyst-triggered), and
   `LearningEngine.sample_confidence_weight` into one `TradeDecision`, with
   every field populated per the contract below.
2. **Confidence-weighted sizing.** Use the RL memory loop's Thompson
   sample to scale `notional_value` — an under-observed or historically
   losing `(strategy, regime, RSI-bucket)` arm should propose a smaller (or
   zero) size, without any hardcoded special case; this falls out of the
   Beta draw by construction.
3. **Attribution attachment** (once in scope). Immediately after
   constructing a `TradeDecision`, call `core/attribution.py`'s explainer
   and attach the resulting `AttributionRecord` to the same
   `trade_context_db.json` entry — never submit a `TradeDecision` derived
   from the allocation model without an attached explanation once this
   capability is live.
4. **Trade context lifecycle.** Write a `trade_context_db.json` entry on
   every entry decision; update the same entry (never a new one) with
   `exit_timestamp`/`pnl` on closure.

## Required `TradeDecision` contract

Every `TradeDecision` returned must populate exactly the fields
`main.py._evaluate_and_submit` and `risk_manager.ProposedTrade` need:
`ticker`, `sector`, `strategy`, `regime_label`, `rsi_14`, `notional_value`,
`entry_price`, `stop_price`, and optionally `take_profit_price`.

- `regime_label` and `strategy` must be formatted consistently across
  calls (e.g. always `"LOW_VOL"`, never `"low_vol"` sometimes) — they
  compose `learning_engine.context_key`; inconsistent formatting fragments
  the bandit's own arms.
- `stop_price` must always be set — the 1%-max-risk rule assumes a defined
  stop. `take_profit_price` is genuinely optional; inventing a target when
  the spec doesn't define one for a given tier is this module's call, not
  `order_executor.py`'s.

## Acceptance criteria

- Every `TradeDecision` this module returns has been round-tripped through
  `risk_manager.ProposedTrade` construction in a test without raising —
  i.e., its fields are always well-formed inputs to the veto layer.
- `regime_label`/`strategy` string formatting is covered by a test
  asserting the same logical regime always produces byte-identical string
  output across repeated calls.
- Once SHAP attribution ships: no `TradeDecision` reaches
  `_evaluate_and_submit` without a corresponding `AttributionRecord`
  already written to `trade_context_db.json` for that decision — enforced
  by a test, not just code review.
- `evaluate_catalyst` has a test covering `filtered_probs=None` explicitly
  — the news pipeline can fire before the structural loop has ever run for
  a ticker.

## Coding standards

Follow [Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md),
[Standards/Coding Standards.md](Standards/Coding%20Standards.md), and
[Standards/Model Explainability Standard.md](Standards/Model%20Explainability%20Standard.md)
once attribution is in scope. Orchestration-specific additions:

- `evaluate_bar` and `evaluate_catalyst` are the only two public entry
  points on `SignalGenerator` — all allocation-model inference,
  confidence-weight sampling, and attribution calls happen inside these,
  never exposed as separate public methods other modules could call
  directly and bypass the veto layer.
- No call to `OrderExecutor` or `risk_manager` from this module — return a
  `TradeDecision` and let `main.py._evaluate_and_submit` own the
  veto-then-submit sequence.

## Communication protocols

- Any change to the regime label taxonomy or strategy naming is announced
  to [Memory Engineer](05_MEMORY_ENGINEER.md) before merge — the bandit's
  existing posteriors are keyed on these strings, and a silent rename
  fragments accumulated learning without any error being raised anywhere.
- SHAP findings surfaced by [Quant Researcher](04_QUANT_RESEARCHER.md)
  that suggest the allocation model is relying on a spurious feature are
  treated as release-blocking for any pending deployment until reviewed.
- Every new strategy addition is proposed using
  [Prompt Templates/New Strategy Proposal.md](Prompt%20Templates/New%20Strategy%20Proposal.md)
  before implementation begins.

## Must escalate

- Any change to the `TradeDecision` dataclass or the `SignalGenerator`
  `Protocol` shape — both are defined in `main.py`, owned by
  [System Architect](01_SYSTEM_ARCHITECT.md).
- The FinBERT catalyst threshold value — confirm against the spec rather
  than eyeballing a plausible number.
- Extending `learning_engine.py`'s context key beyond `(strategy,
  regime_label, rsi_bucket)` — explicitly flagged there as a deliberate,
  separate decision.
- Shipping the allocation model to paper trading before it has a SHAP
  summary reviewed per [Quant Researcher](04_QUANT_RESEARCHER.md)'s
  acceptance criteria.

## Pitfalls specific to this seam (anticipated, since the module doesn't exist yet)

- `evaluate_bar` receives `filtered_probs` post-stability-filter — don't
  re-implement debouncing here; `StabilityFilter` already guarantees
  3-bar-consistent state before calling in.
- `evaluate_catalyst` receives `filtered_probs` that may be `None` — handle
  explicitly rather than assuming a regime is always known.
- Don't let attribution computation block order submission — per
  [Quant Researcher](04_QUANT_RESEARCHER.md)'s coding standards, if SHAP
  computation isn't sub-100ms, attach it slightly after submission rather
  than delaying the trade on an explanation.
