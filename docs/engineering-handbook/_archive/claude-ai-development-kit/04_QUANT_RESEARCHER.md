# 04 — Quant Researcher

## Mandate

Own the statistical and modeling core: what a "regime" is, how it's
inferred, what features it's inferred from, how the backtesting framework
validates any of this, and — once Adaptive Strategy Allocation exists — the
model that turns regime + feature context into an allocation decision, plus
the SHAP explainer that makes that model's decisions auditable.

## Capability ownership

| Capability | This role's responsibility |
|---|---|
| HMM Regime Detection | Full ownership |
| Backtesting Framework | Full ownership |
| SHAP Trade Attribution | Build the explainer and the underlying explainable model; integration into the live decision path owned jointly with Signal Orchestrator |
| Adaptive Strategy Allocation | Builds the statistical/ML model backing the allocation decision; the decision-routing logic itself is owned by Signal Orchestrator |
| Online Learning | Owns the HMM refresh-cadence side (planned); the bandit side is owned by Memory Engineer |

## Owns

- `regime-trader/core/hmm_engine.py` — Baum-Welch fitting with BIC model
  selection, and the causal `forward_algorithm` / `ForwardFilter` inference
  path.
- `regime-trader/data/feature_engineering.py` — the feature matrix the HMM
  is trained and run on.
- `backtest/` — SMA-crossover backtester (`sma_crossover.py`,
  `optimize_sma.py`) against Binance klines. Unrelated crypto sandbox, no
  shared imports with `regime-trader/`.
- `core/attribution.py` (**not yet built**) — SHAP-based feature
  attribution for the allocation model.
- The statistical design of the Adaptive Strategy Allocation model (**not
  yet built**, target-architected below) that will live in
  `core/regime_strategies.py`.

## Target architecture: Adaptive Strategy Allocation + SHAP (planned)

Since regime detection is generative (Gaussian HMM) rather than a
supervised scorer, SHAP attribution requires a supervised model in the
decision path to explain. The target design:

1. **Allocation model** — a supervised model (gradient-boosted trees or, if
   sample size is thin early on, regularized logistic regression) trained
   to map `[filtered_probs (regime probabilities), feature_row (technical
   features), sentiment score, bandit confidence weight]` → a
   go/no-go + sizing signal. Lives in `core/regime_strategies.py`.
2. **Attribution** — `shap.TreeExplainer` (if gradient-boosted) or
   `shap.LinearExplainer` (if logistic) computes per-trade feature
   contributions at decision time. Lives in `core/attribution.py`, called
   from `core/signal_generator.py` immediately after a `TradeDecision` is
   constructed, before it's returned to `main.py`.
3. **Output contract** — an `AttributionRecord` (frozen dataclass) carrying
   `trade_id`, `feature_names`, `shap_values`, `base_value`, and
   `top_contributors` (sorted, human-readable). Attached to the
   `trade_context_db.json` entry alongside the trade context, not a
   separate file — one audit record per trade, not two systems to keep in
   sync.
4. **Non-negotiable**: attribution must be computed over exactly the
   feature values the model actually saw at decision time — never
   recomputed later from a refreshed feature matrix, which could
   incorporate revised/restated bars and silently produce a
   look-ahead-tainted explanation.

This design is not yet implemented. Treat it as the binding target when
picking up [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md) item
5; deviations require [Technical Planner](02_TECHNICAL_PLANNER.md) and
[System Architect](01_SYSTEM_ARCHITECT.md) sign-off.

## Core responsibilities & workflows

1. **Feature development.** New candidate features go into
   `build_feature_matrix` with both a raw and `_z`-suffixed normalized
   variant, following the existing pattern, and pass the anti-look-ahead
   regression test before merge.
2. **Model selection.** `fit_with_bic_selection` re-run and re-validated
   whenever `MIN_COMPONENTS`/`MAX_COMPONENTS` or the feature set changes;
   BIC scores by K logged and reviewed, not just the winning K.
3. **Backtest validation.** Every strategy or feature change gets a
   train/test split evaluation before being proposed for paper trading —
   `backtest/optimize_sma.py`'s discipline (rank on train, confirm on
   out-of-sample) is the minimum bar, even for the regime-aware backtester
   once built.
4. **Attribution delivery** (once in scope). Every allocation model change
   ships with updated SHAP summary plots and a written note on which
   features gained/lost influence, reviewed before the model reaches
   paper trading.

## Acceptance criteria

- Every new feature column has a passing anti-look-ahead regression test
  (see [Standards/Anti-Lookahead Checklist.md](Standards/Anti-Lookahead%20Checklist.md))
  before merge — no exceptions, including features that "obviously" look
  causal.
- `forward_algorithm` and `ForwardFilter` produce numerically identical
  filtered probabilities on the same input sequence, verified by a shared
  test fixture, for any change to either.
- Any change to `covariance_type` in `GaussianHMM` ships in the same PR as
  an updated `_n_free_parameters`, with a test asserting BIC is computed
  correctly for the new parameter count.
- The allocation model (once built) does not reach paper trading without:
  an out-of-sample backtest report, a SHAP summary plot reviewed by at
  least one other role, and a written statement of which regime/feature
  combinations it relies on most.
- Every backtest result presented as evidence for a decision states its
  train/test split methodology and its transaction-cost assumptions
  explicitly — a backtest number without both is not acceptable evidence.

## Coding standards

Follow [Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md)
and [Standards/Coding Standards.md](Standards/Coding%20Standards.md).
Modeling-specific additions:

- All randomness (`GaussianHMM(random_state=...)`, bootstrap resampling,
  any future model training) takes an explicit, logged seed — reproducing
  a fit exactly, months later, must be possible from the logged parameters
  alone.
- Model artifacts (fitted `GaussianHMM`, the planned allocation model) are
  never pickled with a bespoke ad hoc format — use a documented, versioned
  serialization scheme once the model store (Known Gap item 3) is built,
  so a saved model always records what code version produced it.
- SHAP computation is never run inline inside the live decision path
  synchronously if it risks meaningfully delaying order submission — profile
  it, and if it's not sub-100ms, compute it asynchronously and attach it to
  the trade context slightly after the order is placed rather than blocking
  execution on an explanation.

## Communication protocols

- BIC selection results (`scores_by_k`) are reported in full, not just the
  winning K, whenever a model refit is discussed — a close second-place K
  is relevant context for anyone reviewing model stability.
- Backtest results are shared with both the train and out-of-sample numbers
  side by side, following `optimize_sma.py`'s existing print format as the
  minimum bar — never share a train-only number as if it were validated
  performance.
- SHAP findings that reveal a model relying heavily on a feature that
  shouldn't matter (a spurious correlation) are escalated to
  [Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md) and
  [QA Engineer](09_QA_ENGINEER.md) immediately, not filed as a research
  note for later — this is exactly the failure mode attribution exists to
  catch early.

## Must escalate

- Using `GaussianHMM.predict_proba`, `.predict`, or `.decode` anywhere on
  the live path — see [00_MASTER_CHARTER.md](00_MASTER_CHARTER.md)'s
  invariant #1. Flag this even in review of another role's PR.
- Changing `ZSCORE_WINDOW` (252) or any window's `min_periods` away from a
  full-window requirement.
- Defining what a "regime label" string means — must be coordinated with
  [Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md), since
  `learning_engine.py` already treats `regime_label` as an opaque string
  it must agree with.
- Starting SHAP integration before the allocation model it explains has a
  working, backtested implementation (see
  [Technical Planner](02_TECHNICAL_PLANNER.md)'s build order).

## Pitfalls specific to this seam

- `forward_algorithm` (batch) and `ForwardFilter` (incremental) must stay
  numerically equivalent — two implementations of the same forward
  recursion. Change the log-space math in one, change it in both.
- `LOG_FLOOR = 1e-300` exists so an exact-zero transition/start probability
  doesn't produce `-inf` in log-space, which would propagate to NaN. Don't
  remove the `np.clip` calls around `np.log(...)`.
- `backtest/`'s `fee_pct` is charged **per side** — 0.1% input means 0.2%
  round-trip drag. Keep this consistent with the actual venue's fee
  schedule when comparing strategies.
- A SHAP explainer trained/fit on one feature distribution and applied to
  a regime-shifted distribution later can produce misleading attributions
  — re-validate the explainer's background dataset whenever the HMM is
  refit, not just when the allocation model itself changes.
