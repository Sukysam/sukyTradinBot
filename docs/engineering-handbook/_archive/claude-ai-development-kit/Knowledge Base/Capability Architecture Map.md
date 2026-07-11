# Knowledge Base — Capability Architecture Map

Detailed backing for the summary table in
[00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md)'s Capability Ownership Map.
Where the master table answers "who owns this and is it built," this
document answers "how does it actually work, and how does it relate to
every other capability." Update both documents together.

## 1. Hidden Markov Model Regime Detection — Implemented

**What**: a Gaussian HMM (`hmmlearn.hmm.GaussianHMM`, `covariance_type="full"`),
fit per ticker via Baum-Welch/EM with BIC-based component-count selection
(3–7 states), run live through a strictly causal forward filter.

**Modules**: `core/hmm_engine.py`, `data/feature_engineering.py`.

**Feeds**: Adaptive Strategy Allocation (regime probabilities are a primary
input), the RL memory loop (regime label is part of the bandit's context
key), Risk Manager's correlation filter indirectly (shares the same
`log_returns` computation).

**Full detail**: `04_QUANT_RESEARCHER.md`, `Standards/Anti-Lookahead Checklist.md`.

## 2. Adaptive Strategy Allocation — Interface defined, not yet built

**What**: the logic that turns regime probabilities + technical features +
sentiment + RL confidence weight into a `TradeDecision`. Target design uses
a supervised model (gradient-boosted trees or logistic regression) hosted
in `core/regime_strategies.py`.

**Modules**: `core/signal_generator.py`, `core/regime_strategies.py`
(neither exists yet).

**Feeds**: order execution (via `TradeDecision`), SHAP attribution (the
model to be explained), the RL memory loop (writes trade context on entry
and closure).

**Depends on**: HMM model store (Known Gap item 3).

**Full detail**: `07_SIGNAL_ORCHESTRATOR.md`, `Architecture/Known Gaps.md` item 4.

## 3. Reinforcement Learning Memory Loop — Implemented

**What**: a contextual multi-armed bandit (Thompson Sampling over
Beta-Bernoulli posteriors) keyed on `(strategy, regime_label, rsi_bucket)`,
learning from closed-trade outcomes stored in `trade_context_db.json`.

**Modules**: `core/learning_engine.py`.

**Feeds**: Adaptive Strategy Allocation (confidence weight scales position
size).

**Full detail**: `Architecture/Reinforcement Learning Memory Loop.md`,
`05_MEMORY_ENGINEER.md`.

## 4. Online Learning — Implemented (bandit) / Planned (HMM)

**What**: two distinct mechanisms sharing the "online learning" label —
(a) the RL memory loop's weekly incremental posterior update (implemented,
see #3), and (b) HMM refresh cadence (planned, no implementation or even a
finalized design yet).

**Modules**: `core/learning_engine.py` (a); none yet (b).

**Full detail**: `SOPs/Model Retraining and Online Learning.md`.

## 5. SHAP Trade Attribution — Planned

**What**: per-trade feature attribution for the Adaptive Strategy
Allocation model, using `shap.TreeExplainer` or `shap.LinearExplainer`
depending on the model type chosen, attached to `trade_context_db.json`
entries.

**Modules**: `core/attribution.py` (not yet built).

**Depends on**: Adaptive Strategy Allocation (#2) having a working
implementation — attribution cannot precede what it explains.

**Full detail**: `Architecture/SHAP Trade Attribution.md`,
`Standards/Model Explainability Standard.md`.

## 6. FinBERT NLP News Engine — Implemented

**What**: `ProsusAI/finbert` headline sentiment scoring into
`{positive, negative, neutral}` probabilities.

**Modules**: `core/sentiment_engine.py`.

**Feeds**: the Catalyst Strategy trigger (owned by Adaptive Strategy
Allocation, #2) via the event-driven news pipeline.

**Full detail**: `06_NLP_ENGINEER.md`.

## 7. Event-Driven Execution — Implemented

**What**: two independent trigger mechanisms for trade evaluation — a
5-minute polling structural loop, and an event-driven news WebSocket
listener — running concurrently under one `asyncio` event loop alongside a
weekend cron.

**Modules**: `main.py`, `broker/news_streamer.py`.

**Full detail**: `Architecture/System Overview.md`, `01_SYSTEM_ARCHITECT.md`.

## 8. Alpaca Broker Integration — Partial

**What**: order construction/submission (implemented) and historical
market data fetching (not yet built).

**Modules**: `broker/order_executor.py` (implemented); `broker/alpaca_client.py`
(not yet built).

**Full detail**: `03_BACKEND_ENGINEER.md`, `Architecture/Known Gaps.md` item 2.

## 9. Backtesting Framework — Implemented (baseline) / Planned (regime-aware)

**What**: a crypto SMA-crossover grid-search backtester with a train/test
split (implemented, `backtest/`), and a regime-aware equity backtester that
can replay the actual structural-loop decision path offline (planned,
depends on items 2 and 8 of `Architecture/Known Gaps.md`).

**Modules**: `backtest/sma_crossover.py`, `backtest/optimize_sma.py`
(implemented); no module yet for the regime-aware version.

**Full detail**: `04_QUANT_RESEARCHER.md`.

## 10. Risk Management & Circuit Breakers — Implemented

**What**: a stateless veto layer (exposure, concentration, leverage,
correlation, per-trade risk limits) plus PnL-based circuit breakers
(size cut, daily/weekly halt, emergency hard stop) with a human-cleared
disk lock file.

**Modules**: `core/risk_manager.py`.

**Full detail**: `08_RISK_MANAGER.md`, `Standards/Risk Limits Reference.md`.

## 11. Production Deployment — Implemented (process) / Planned (orchestration)

**What**: a single supervised `asyncio` process (implemented); orchestrated,
monitored, model-serving-aware deployment infrastructure (planned).

**Modules**: `main.py` (lifecycle); no dedicated deployment tooling yet.

**Full detail**: `Architecture/Production Deployment.md`, `12_DEVOPS_ENGINEER.md`.

## Dependency graph (capability numbers above)

```
1 (HMM) ──┬──► 2 (Adaptive Allocation) ──┬──► 5 (SHAP Attribution)
          │                                │
8 (Alpaca│data client, planned) ──────────┤
          │                                │
3 (RL loop) ───────────────────────────────┘
          │
4a (bandit online learning) [same module as 3]
4b (HMM refresh, planned) ──► depends on model store, feeds back into 1

6 (FinBERT) ──► feeds 2's catalyst trigger

7 (event-driven execution) — orchestrates 1, 2, 6's live invocation
10 (risk management) — gates every TradeDecision from 2, independent of all model capabilities
9 (backtesting) — validates 1 and 2 offline
11 (production deployment) — runs and monitors the whole system
```
