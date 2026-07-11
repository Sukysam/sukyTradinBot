# Glossary

**Arm** — In `learning_engine.py`, one `(strategy, regime_label,
rsi_bucket)` context key, tracked as an independent Beta-Bernoulli posterior
(`BetaArm`). Terminology from the multi-armed bandit framing of the
continuous learning loop.

**BIC (Bayesian Information Criterion)** — Model-selection score used in
`hmm_engine.fit_with_bic_selection` to choose the HMM component count
(`MIN_COMPONENTS`–`MAX_COMPONENTS`) that best trades off fit quality against
model complexity, penalizing free-parameter count.

**Catalyst Strategy** — The event-driven trade path triggered by breaking
news sentiment (FinBERT >0.90 positive while HMM regime reads NEUTRAL),
independent of the 5-minute structural loop. Owned by
`signal_generator.evaluate_catalyst` (not yet built).

**Circuit breaker** — A PnL-based automatic trading restriction
(`risk_manager.CircuitBreakerAction`): none, 50% size cut, daily halt,
weekly halt, or emergency hard stop, escalating with drawdown severity.

**Emergency hard stop** — The most severe circuit breaker, triggered at
>10% peak drawdown. Writes a disk-backed lock file
(`risk_manager.EMERGENCY_HALT.lock`) that must be manually deleted by a
human to resume trading — the one piece of state in `risk_manager.py` that
isn't a pure function of its call-time inputs.

**Forward filter / Forward algorithm** — The causal (non-look-ahead)
inference method for HMM state probabilities, `P(S_t | X_{1:t})`.
`forward_algorithm` is the batch version (backtesting); `ForwardFilter` is
the O(1)-per-update incremental version (live loop). Never confuse with
Viterbi decoding or forward-backward smoothing, both of which use future
observations.

**Notional value** — Dollar size of a position (as opposed to share
quantity). `ProposedTrade.quantity` derives share count from notional /
entry price; `OrderExecutor.size_to_shares` does the same truncated to whole
shares for order submission.

**Regime** — The latent HMM state a ticker is inferred to be in at a given
bar, based on volatility/trend/momentum features. Exposed as a probability
distribution over states (`filtered_probs`) and, after the 3-bar stability
filter, as a single argmax state.

**Stability filter** — `main.py.StabilityFilter`: only emits a regime state
once the same argmax state has held for `STABILITY_PERSISTENCE_BARS` (3)
consecutive forward-filter updates, preventing a single noisy bar from
flip-flopping the strategy target.

**Thompson Sampling** — The exploration/exploitation strategy used by
`LearningEngine.sample_confidence_weight`: draws a random sample from each
arm's Beta posterior rather than always picking the highest posterior mean,
so under-observed arms still get occasionally explored.

**Trade context** — One entry in `data/trade_context_db.json`
(`learning_engine.TradeContext`): a snapshot of the strategy, regime, RSI,
and eventual PnL for a single trade, written by `signal_generator.py` and
consumed by the weekly learning-engine cron.

**Veto** — The output of `risk_manager.evaluate_trade`
(`VetoDecision`): approve/reject plus an optional size multiplier. The
mandatory gate between a proposed trade and order submission.

**Z-score (rolling)** — Trailing-window normalization
(`feature_engineering.rolling_zscore`) applied to every raw feature before
it's fed to the HMM, using a 252-bar window with `min_periods=window` so no
value is emitted from a partial window.
