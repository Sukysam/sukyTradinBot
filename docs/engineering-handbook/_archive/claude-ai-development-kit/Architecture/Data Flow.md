# Architecture — Data Flow

Traces a single trade idea from raw market data to a submitted order, and
separately, how a closed trade feeds back into future sizing decisions. Some
steps depend on components in [Known Gaps.md](Known%20Gaps.md) that don't
exist yet — marked `(not yet built)`.

## Entry path (structural loop)

```
Alpaca OHLCV bars
   │  MarketDataProvider.get_ohlcv_history()          (not yet built: broker/alpaca_client.py)
   ▼
raw OHLCV DataFrame  [open, high, low, close, volume]
   │  feature_engineering.build_feature_matrix()
   ▼
feature matrix  [log_return_1/5/20, volatility_20, log_volume, adx_14,
                 rsi_14, momentum_20, atr_14]  +  each _z-normalized
   │  take latest row, select *_z columns
   ▼
z-scored feature vector (skipped if any *_z is NaN — warmup incomplete)
   │  ForwardFilter.update()  [model from ModelStore.get_model(), not yet built]
   ▼
filtered_probs: P(regime | history up to now)   ── numpy array over HMM states
   │  StabilityFilter.update()
   ▼
stable regime state (int) — None unless same argmax held 3 consecutive bars
   │  SignalGenerator.evaluate_bar(ticker, filtered_probs, feature_row)   (not yet built: core/signal_generator.py)
   ▼
TradeDecision | None
   │  (if not None)
   ▼
risk_manager.evaluate_trade(ProposedTrade, PortfolioState, price_history_cache)
   │
   ├─ rejected → logged, nothing submitted
   ▼ approved (size_multiplier applied to notional_value)
OrderExecutor.submit_entry_order()
   │
   ▼
Alpaca bracket/OTO order (BUY, whole shares, mandatory stop, optional take-profit)

   (in parallel, non-blocking, once built — see Architecture/SHAP Trade Attribution.md)
   core/attribution.py explains the TradeDecision's allocation-model inputs
   → AttributionRecord appended to the same trade_context_db.json entry
```

## Entry path (news catalyst)

```
Alpaca News WebSocket
   │  NewsStreamer._handle_raw_news()
   ▼
NewsItem (headline, summary, symbols, source, created_at)
   │  filter to watchlist tickers
   ▼
SentimentEngine.score(headline)
   ▼
SentimentScore (positive/negative/neutral probs + label)
   │  SignalGenerator.evaluate_catalyst(news, sentiment, last_known_filtered_probs)   (not yet built)
   ▼
TradeDecision | None  ──► same risk_manager.evaluate_trade → OrderExecutor path as above
```

## Feedback path (learning loop)

```
signal_generator.py writes on entry   (not yet built — sole writer of this file)
   ▼
data/trade_context_db.json entry: {trade_id, strategy, regime_label, rsi_14,
                                    entry_timestamp, exit_timestamp: null, pnl: null}
   │  (later) position closes — signal_generator.py updates the same entry
   ▼
{..., exit_timestamp: <iso8601>, pnl: <float>}
   │  weekend cron (Saturdays): LearningEngine.run_weekly_optimization()
   ▼
context_key(strategy, regime_label, rsi_14) → BetaArm.update(won=pnl>0)
   │  persisted
   ▼
data/learning_weights.json: {"strategy|regime|rsi_bucket": {alpha, beta}, ...}
   │  read live by:
   ▼
LearningEngine.sample_confidence_weight() ── called by signal_generator.py (not yet built)
   at decision time, to scale a new TradeDecision's notional_value
```

This is the loop that makes the system adaptive: a setup that's been
losing accumulates `beta`, its Thompson samples cluster toward zero, and
future proposed trades for that same `(strategy, regime, RSI-bucket)`
combination get sized down — without any code path needing to special-case
"this setup is currently bad," since it falls out of the Beta posterior
directly. This is the system's Reinforcement Learning memory loop and its
online-learning update mechanism — see
[Reinforcement Learning Memory Loop.md](Reinforcement%20Learning%20Memory%20Loop.md)
for the full RL-formulation writeup.

## Portfolio state (read every structural tick, not persisted itself)

```
TradingClient.get_account() + .get_all_positions()
   │  combined with EquityTracker (persisted: data/equity_tracker_state.json)
   ▼
PortfolioState {equity, positions, equity_start_of_day, equity_start_of_week, equity_peak}
   │  feeds both:
   ├─► evaluate_circuit_breakers()  — drawdown-based halts/liquidation
   └─► check_exposure_limits() / check_correlation_filter()  — per-trade veto
```
