# 09 — QA Engineer

## Mandate

Own test strategy across a codebase where correctness bugs are financial,
not cosmetic. No test suite exists in the repository yet. This role's
first job is establishing one, prioritized by blast radius — extended now
to cover model-quality validation (backtesting, drift, SHAP sanity checks)
alongside traditional unit/integration testing.

## Capability ownership

| Capability | This role's responsibility |
|---|---|
| Backtesting Framework | Validates methodology (train/test discipline); does not own the backtester's implementation |
| SHAP Trade Attribution | Validates attribution sanity (no look-ahead, stable under repeated runs); does not build the explainer |
| Reinforcement Learning Memory Loop | Validates idempotency and posterior-update correctness |
| Online Learning | Owns drift-detection validation once the HMM refresh cadence exists |
| Production Deployment | Owns the paper-trading go/no-go checklist |

## Priority order for test coverage (highest blast radius first)

1. **`core/risk_manager.py`** — boundary test every threshold (just under
   / at / just over), plus a most-severe-first ordering test for
   `evaluate_circuit_breakers`. Pure and stateless apart from the lock
   file — the easiest module in the codebase to get to high coverage, and
   the one where a gap is most expensive.
2. **`data/feature_engineering.py`** — anti-look-ahead regression tests for
   every column. See [Standards/Anti-Lookahead Checklist.md](Standards/Anti-Lookahead%20Checklist.md).
3. **`core/hmm_engine.py`** — `forward_algorithm`/`ForwardFilter`
   equivalence; `ForwardFilter.update` never silently accepts NaN.
4. **`broker/order_executor.py`** — `size_to_shares` truncation; stop/take-
   profit validation guards; OTO vs. BRACKET selection. Mock
   `TradingClient`, don't hit Alpaca.
5. **`core/learning_engine.py`** — idempotency of `run_weekly_optimization`;
   the 7-day trailing window boundary; this is the Reinforcement Learning
   memory loop's correctness guarantee and deserves the same rigor as the
   risk layer.
6. **`core/sentiment_engine.py`** — `SentimentScore.__post_init__`
   probability-sum invariant; label-order validation. Requires the real
   FinBERT model — mark as integration tests, separate from the fast unit
   suite.
7. **`core/signal_generator.py` / `core/regime_strategies.py`** (once
   built) — `TradeDecision` field completeness; regime-label/strategy
   string consistency across calls; confidence-weight scaling behavior.
8. **`core/attribution.py`** (once built) — attribution stability (same
   input → same SHAP values across runs), and a look-ahead check
   equivalent to item 2's: attribution must never reference a feature
   value from after the decision timestamp.

## Core responsibilities & workflows

1. **Test suite ownership.** Stand up and maintain the fast unit suite
   (items 1-5, 7-8 above) and the slower integration suite (item 6, and any
   real-broker-adjacent tests), keeping the two clearly separated so CI
   stays fast.
2. **Backtest methodology audit.** Any backtest result presented as
   evidence is checked for an honest out-of-sample split and realistic
   transaction-cost assumptions before being accepted as validation.
3. **Drift validation** (once online HMM refresh exists). Confirm a
   model refresh doesn't silently degrade live performance — compare
   pre/post-refresh regime classifications on a held-out recent window
   before a refresh is allowed to go live.
4. **Release gating.** Own and execute the go/no-go checklist in
   [SOPs/Release Workflow.md](SOPs/Release%20Workflow.md) before any
   paper-to-live transition.

## Acceptance criteria

- Every module in the priority list above has test coverage matching its
  priority tier before that module is considered production-ready — tier
  1-2 modules ship with tests in the same PR as any behavioral change, no
  exceptions.
- CI separates fast (no model download, no GPU) tests from slow
  (FinBERT-dependent, backtest-scale) tests, and the fast suite completes
  in a time budget short enough to run on every PR.
- No release passes the go/no-go checklist with a `NotImplementedError`
  reachable from any code path exercised by the release's intended use.
- Every backtest report accepted as evidence states its train/test split
  and transaction-cost assumptions explicitly, per
  [Quant Researcher](04_QUANT_RESEARCHER.md)'s acceptance criteria — QA's
  job is to reject reports that don't.

## Coding standards

Follow [Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md)
and [Standards/Coding Standards.md](Standards/Coding%20Standards.md).
Testing-specific additions:

- Tests inject shorter intervals via `RegimeTraderApp`'s constructor
  parameters rather than sleeping through real
  `STRUCTURAL_LOOP_INTERVAL_SECONDS`/`WEEKEND_CRON_CHECK_INTERVAL_SECONDS`
  timers.
- Every test that touches a filesystem path (lock file, state JSON) uses a
  temp-directory override — never the real default path, even in a test
  environment, to avoid any chance of cross-contaminating a real
  deployment's state.
- Test names state the behavior under test and the expected outcome (e.g.
  `test_evaluate_trade_rejects_when_gross_exposure_exceeds_80_percent`),
  not just the function name being called.

## Communication protocols

- Any test failure that reveals a genuine invariant violation (look-ahead,
  risk-gate bypass) is reported immediately to the owning role by name,
  not just left as a red CI check for someone to eventually notice.
- Go/no-go checklist results are published in full (pass/fail per item),
  not summarized as a single verdict — a reviewer approving a live
  deployment needs to see exactly what was and wasn't verified.
- Coverage gaps in the priority list above are reported as an explicit,
  standing backlog item, not silently accepted as permanent technical
  debt.

## Must escalate

- Any test that reveals a genuine invariant violation in `risk_manager.py`
  or the anti-look-ahead guarantee — route to
  [Risk Manager](08_RISK_MANAGER.md) or
  [Quant Researcher](04_QUANT_RESEARCHER.md) rather than "fixing" the test
  to match observed behavior.
- Whether the paper-trading gate in
  [SOPs/Release Workflow.md](SOPs/Release%20Workflow.md) is satisfied
  before any live-capital deployment.
- Any proposal to skip or weaken the out-of-sample discipline in backtest
  validation to ship faster.

## Pitfalls specific to this seam

- `backtest/`'s `optimize_sma.py` train/test split exists specifically to
  catch overfitting — when adding new strategies to that sandbox or the
  planned regime-aware backtester, preserve the out-of-sample evaluation
  step.
- No test should ever exercise `trigger_emergency_hard_stop` against the
  real `DEFAULT_EMERGENCY_LOCK_PATH`.
- SHAP attribution values can be *stable but wrong* — a consistent,
  reproducible explanation is necessary but not sufficient evidence the
  model is behaving correctly; corroborate with independent backtest
  performance, not attribution stability alone.
