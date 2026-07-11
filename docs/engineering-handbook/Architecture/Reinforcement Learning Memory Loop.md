# Architecture — Reinforcement Learning Memory Loop

Status: **Implemented**. Owner: [05_MEMORY_ENGINEER.md](../05_MEMORY_ENGINEER.md).

## Formulation

`core/learning_engine.py` implements a **contextual multi-armed bandit** —
a canonical, well-studied reinforcement-learning formulation for problems
where each decision's context determines its own independent reward
distribution, rather than requiring a full sequential-decision-process
model.

| RL concept | Concrete implementation |
|---|---|
| Context / state | `(strategy, regime_label, rsi_bucket)` — `learning_engine.context_key` |
| Arm | One context key, tracked as an independent `BetaArm` posterior |
| Reward | Binary: `pnl > 0` on trade close |
| Memory / experience replay | `data/trade_context_db.json` — every trade's context and eventual outcome |
| Value function | `BetaArm.posterior_mean` — `alpha / (alpha + beta)` |
| Policy | Thompson Sampling — `BetaArm.sample(rng)` draws from the posterior rather than always exploiting the mean |
| Policy execution | `LearningEngine.sample_confidence_weight`, called by `signal_generator.py` (planned) at decision time to scale position size |
| Learning update | `BetaArm.update(won)` — `alpha += 1` on a win, `beta += 1` on a loss |
| Persistent value store | `data/learning_weights.json` |

## Why Thompson Sampling, not greedy exploitation

A policy that always sized up the single best-known arm would stop
exploring new or thin-data setups entirely, and would be overconfident
early — a `(strategy, regime, RSI-bucket)` combination with 2 wins and 0
losses has a posterior mean of 1.0 but enormous uncertainty. Thompson
Sampling's random draw from the full Beta posterior naturally trades off
exploration and exploitation without any explicit epsilon-greedy schedule
or manual tuning — an arm with wide uncertainty occasionally samples high
(exploration), while an arm with a long, consistent losing record clusters
its samples near zero (exploitation).

## Data flow

```
Trade closes (pnl known)
   │  signal_generator.py updates the trade_context_db.json entry
   ▼
TradeContext {trade_id, strategy, regime_label, rsi_14, exit_timestamp, pnl}
   │  (accumulates all week)
   ▼
Weekend cron (Saturday, hourly-polled, idempotency-guarded):
LearningEngine.run_weekly_optimization(trade_context_db_path, as_of)
   │  for each trade closed in the trailing 7 days:
   │    context_key(strategy, regime_label, rsi_14) → BetaArm.update(pnl > 0)
   ▼
data/learning_weights.json  {"strategy|regime|rsi_bucket": {alpha, beta}, ...}
   │  read live, every decision:
   ▼
LearningEngine.sample_confidence_weight(strategy, regime_label, rsi_14)
   │  scales notional_value in the next TradeDecision for this context
   ▼
(loop closes: the next trade using this arm's outcome updates the same arm)
```

## Why weekly, not per-trade, updates

Updating posteriors immediately on every trade close (true online, per-event
updating) was considered and rejected in favor of the batched weekly cadence
for two reasons: (1) it keeps `LearningEngine`'s write path single-threaded
and simple — one writer, once a week, rather than a live process
concurrently reading and writing `learning_weights.json` on every position
close; (2) it matches the spec's Sec. 6 weekend-cron design. This is still
genuinely "online learning" in the sense that matters operationally — the
system adapts within a live deployment without a full retrain or redeploy
— just not event-at-a-time online.

## Idempotency guarantee

`run_weekly_optimization`'s trailing 7-day window plus `main.py`'s
`_last_weekly_run_marker` (ISO week string) together guarantee a trade
closed once is never double-counted across consecutive weekly runs, even
if the cron's hourly poll fires multiple times within the same eligible
window. This property is load-bearing — see
[09_QA_ENGINEER.md](../09_QA_ENGINEER.md)'s acceptance criteria for the
required test.

## Deliberate scope boundary

The context key is exactly `(strategy, regime_label, rsi_bucket)` — the
spec's own example ("RSI > 70 in a BULL regime"). Extending it to bucket
on additional dimensions (ADX, volatility) would multiply the arm count and
dilute the sample count per arm, weakening the statistical power of every
posterior. Treat any such extension as a deliberate, reviewed decision
(see [02_TECHNICAL_PLANNER.md](../02_TECHNICAL_PLANNER.md)), not a natural
next increment.

## Relationship to other capabilities

- **Adaptive Strategy Allocation** (planned) consumes this loop's
  confidence weight as one of several inputs to its sizing decision — the
  bandit is not itself the allocation model, it's one signal feeding it.
- **SHAP Trade Attribution** (planned), once built, will include the
  bandit's confidence weight as an explainable feature in the allocation
  model, making its influence on any given trade visible in the
  attribution record — see
  [Architecture/SHAP Trade Attribution.md](SHAP%20Trade%20Attribution.md).
