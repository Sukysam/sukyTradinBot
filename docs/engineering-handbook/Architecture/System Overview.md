# Architecture — System Overview

## Two independent codebases in this repo

- `regime-trader/` — the live/paper equity trading system. Everything below
  describes this.
- `backtest/` — a standalone crypto SMA-crossover backtester against
  Binance public klines. No shared code, no shared risk, separate concern.

## `regime-trader/` at a glance

One process (`main.py: RegimeTraderApp`), one `asyncio` event loop, three
independent concurrent pipelines:

```
                         ┌─────────────────────────────────────┐
                         │      RegimeTraderApp.run()           │
                         │      asyncio.gather(...)             │
                         └───────────────┬───────────────────────┘
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
   ┌──────────▼──────────┐   ┌───────────▼───────────┐   ┌──────────▼──────────┐
   │ 1. Structural loop   │   │ 2. News listener       │   │ 3. Weekend cron      │
   │    every 5 min       │   │    event-driven        │   │    hourly poll,      │
   │                       │   │                        │   │    fires Saturdays  │
   └──────────┬───────────┘   └───────────┬────────────┘   └──────────┬──────────┘
              │                           │                           │
   OHLCV → features → ForwardFilter   NewsStreamer → SentimentEngine   trade_context_db.json
   → 3-bar stability filter          → evaluate_catalyst()            → LearningEngine
   → evaluate_bar()                                                    .run_weekly_optimization()
              │                           │
              └─────────────┬─────────────┘
                             │
                  TradeDecision (from SignalGenerator)
                             │
                  risk_manager.evaluate_trade()  ◄── the one mandatory gate
                             │
                  OrderExecutor.submit_entry_order()
```

## Pipeline 1 — 5-minute structural loop

`_structural_loop` → `_run_structural_tick` per tick:

1. Build a fresh `PortfolioState` snapshot from Alpaca (`_build_portfolio_state`).
2. `evaluate_circuit_breakers` — if it says liquidate, call
   `OrderExecutor.liquidate_all_positions` and skip the rest of this tick
   entirely.
3. For each ticker: fetch OHLCV history → `build_feature_matrix` →
   `ForwardFilter.update` → `StabilityFilter.update` (needs 3 consecutive
   matching bars to emit) → `SignalGenerator.evaluate_bar` → if a
   `TradeDecision` comes back, `_evaluate_and_submit`.
4. `_evaluate_and_submit`: build a correlation-check price-history cache →
   `risk_manager.evaluate_trade` → if approved, `OrderExecutor.submit_entry_order`.

## Pipeline 2 — event-driven news listener

`NewsStreamer` (wraps Alpaca's `NewsDataStream`, run in a worker thread via
`asyncio.to_thread` since the underlying SDK call owns its own event loop)
→ `_on_news` → filter to relevant tickers → `SentimentEngine.score` →
`SignalGenerator.evaluate_catalyst` (using whatever `filtered_probs` the
structural loop last computed for that ticker, possibly `None`) → same
`_evaluate_and_submit` path as pipeline 1.

## Pipeline 3 — weekend cron

Polled hourly (`_weekend_cron_loop`), fires once per ISO week on Saturday
(`_is_weekend_optimization_due`, idempotency-guarded by
`_last_weekly_run_marker`) → `LearningEngine.run_weekly_optimization` reads
`trade_context_db.json`, updates Beta-Bernoulli posteriors for every closed
trade in the trailing 7 days, persists to `learning_weights.json`.

## What's real today vs. wired-as-placeholder

See [Known Gaps.md](Known%20Gaps.md) for the current list and
[Data Flow.md](Data%20Flow.md) for how data moves through the fully-built
version of this system.

## Related capability-specific architecture

Two capabilities in the Master Charter's Capability Ownership Map warrant
their own dedicated architecture documents rather than a subsection here:

- [Reinforcement Learning Memory Loop.md](Reinforcement%20Learning%20Memory%20Loop.md) —
  how pipeline 3's `LearningEngine` implements online reinforcement
  learning via a contextual bandit.
- [SHAP Trade Attribution.md](SHAP%20Trade%20Attribution.md) — the target
  design for explainable trade decisions, sequenced after Adaptive
  Strategy Allocation (Known Gap item 4).
- [Production Deployment.md](Production%20Deployment.md) — how this
  three-pipeline process actually gets run, monitored, and recovered in a
  live environment.
