# Standard — BacktestResult Contract

Governs `backtest.models.BacktestResult` (and its two embedded record
types, `TradeRecord` and `EquityPoint`), the single output type the
Backtesting & Validation layer (Milestone 8) is expected to produce. See
[Architecture/ADR/ADR-014-BacktestResult-Contract.md](../Architecture/ADR/ADR-014-BacktestResult-Contract.md)
for why this type is frozen *before* `src/backtest/` exists — the same
"freeze interfaces before implementation" discipline established for
every milestone since `RegimeState`. This document is the binding
contract for whoever implements the backtesting engine against it, and
for every consumer (regression/golden-dataset tests, `reporting.py`,
Milestone 9's Adaptive Learning) that reads a `BacktestResult`.

## Why this exists, and why now

Milestone 8's mandate is narrow on purpose: replay historical bars
through the *entire* existing decision pipeline (Market Data → Features
→ HMM → Strategy → Risk → Execution), simulate fills against historical
prices, track portfolio value, and compute performance metrics. It does
**not** retrain models, tune hyperparameters, or optimize strategy
parameters — those are separate concerns (the existing `backtest/`
crypto sandbox's `optimize_sma.py` does parameter sweeps for that
sandbox specifically; this milestone's engine does not inherit that
responsibility).

`BacktestResult` is a genuinely different shape from every contract
frozen so far: `FeatureVector`, `RegimeState`, `StrategyDecision`,
`ExecutionDecision`, and `OrderIntent` are all single-event snapshots.
`BacktestResult` is a **run-level summary** aggregating a full replay —
this is reflected in its size (more fields than any prior contract,
including two embedded record-list types) and in why regression testing
matters so much more here: a `BacktestResult` produced from the same
inputs must be bit-for-bit reproducible, or every backtest result in
this codebase becomes unverifiable.

This contract is not grounded in the existing `backtest/` sandbox in the
way Milestones 4–7 grounded their contracts in `regime-trader/` — that
sandbox is explicitly lower-stakes (see
[00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md) Section 1) and returns
an ad hoc, undocumented `dict` from `sma_crossover.py::backtest`, not a
contract. Where this freeze's field *names* echo that sandbox's existing
convention (`win_rate`, `max_drawdown`) that's a deliberate nod to
established naming, not a port of its logic or shape.

## Scope

Applies to `backtest.models.BacktestResult`, `TradeRecord`, and
`EquityPoint`, and whatever public method the eventual
`backtest.engine` module exposes to produce a `BacktestResult` (signature
not yet fixed — that's implementation, not contract). Does **not**
freeze:

- How fills are simulated (slippage model, whether `OrderIntent.
  reference_price` is treated as the fill price or a more realistic
  model is used) — implementation detail, escalation-worthy per
  [09_QA_ENGINEER.md](../09_QA_ENGINEER.md) if it affects backtest
  credibility, but not fixed by this freeze.
- The replay mechanism itself (`replay.py`) or how `portfolio.py` tracks
  intermediate state during a run — only the final `BacktestResult` this
  milestone hands back is frozen.
- Report rendering (`reporting.py`) — consumes a `BacktestResult`,
  doesn't shape it.

## Required fields — `BacktestResult`

| Field | Type | Guarantee |
|---|---|---|
| `start_date` | `datetime` | UTC. The first bar timestamp actually replayed — not the requested start, if data began later. |
| `end_date` | `datetime` | UTC. The last bar timestamp actually replayed. Must be `>= start_date`. |
| `symbols` | `tuple[str, ...]` | Non-empty. No duplicates. Every symbol actually traded or held during the run. |
| `initial_equity` | `float` | `> 0`. |
| `final_equity` | `float` | `>= 0`. |
| `cagr` | `float` | Compound annual growth rate, as a fraction (`0.12` = 12%/year). Negative for a losing run. |
| `sharpe_ratio` | `float` | Annualized. No fixed bound — can be negative. |
| `sortino_ratio` | `float` | Annualized, downside-deviation-only. No fixed bound. |
| `calmar_ratio` | `float` | `cagr / max_drawdown`. `float("inf")` when `max_drawdown == 0.0` (no drawdown at all) — matches the `inf`-for-degenerate-denominator convention `risk.models.PortfolioState.gross_exposure_pct` already established in this codebase, not a new one. |
| `max_drawdown` | `float` | `[0.0, 1.0]` — the largest peak-to-trough decline in the equity curve, as a fraction. `0.0` only if equity never declined. |
| `win_rate` | `float` | `[0.0, 1.0]`. Fraction of closed trades in `trade_log` with `pnl > 0`. `0.0` when `trade_log` is empty (no trades to win). |
| `profit_factor` | `float` | `gross_profit / gross_loss` (both taken as positive magnitudes), `>= 0.0`. `float("inf")` when there are winning trades and zero losing trades — same convention as `calmar_ratio`. |
| `average_holding_period` | `timedelta` | `>= timedelta(0)`. Mean of every closed trade's `holding_period` in `trade_log`; `timedelta(0)` when `trade_log` is empty. |
| `exposure` | `float` | `[0.0, 1.0]`. Time-weighted fraction of the run during which any capital was deployed (at least one open position) — not a per-symbol figure. |
| `turnover` | `float` | `>= 0.0`. Sum of traded notional (both entries and exits) divided by average equity over the run — no fixed upper bound (a high-turnover strategy can legitimately exceed `1.0`). |
| `trade_log` | `tuple[TradeRecord, ...]` | Every closed trade during the run, ascending by `exit_timestamp`. May be empty (a run with no completed trades). |
| `equity_curve` | `tuple[EquityPoint, ...]` | Non-empty. Strictly ascending by `timestamp`. `equity_curve[0].equity == initial_equity`. |
| `replay_run` | `ReplayRun` | Reproducibility metadata for this specific run — see below. Added during contract review so a regression six months from now can be traced back to exactly which code, contracts, dataset, and versions produced it, not just re-run and hoped to match. |
| `generated_at` | `datetime` | UTC. When this `BacktestResult` was constructed — not `end_date`. |
| `metadata` | `Mapping[str, Any]` | Free-form. **No guaranteed keys yet** — same reasoning as every other contract frozen before its implementation existed. The natural home for run configuration (which strategy config, random seed) not already covered by `replay_run`, once a real implementation defines what it needs there. |

## Required fields — `TradeRecord`

One closed round-trip trade (entry through exit), embedded in
`BacktestResult.trade_log`.

| Field | Type | Guarantee |
|---|---|---|
| `symbol` | `str` | Non-empty. |
| `strategy_id` | `str` | Non-empty. Traceable back to the `StrategyDecision.strategy_id` that opened this trade — the same traceability `ExecutionDecision.strategy_reference` and `OrderIntent.execution_reference` already give a single decision, carried through to the closed-trade record. |
| `regime_id` | `int` | `>= 0`. The regime active when this trade was opened. |
| `side` | `execution.models.OrderSide` | Reused from the Execution Layer contract rather than a new enum — a closed trade is always a `BUY` entry (invariant #5: long-only) matched with a later `SELL` exit. |
| `entry_timestamp` | `datetime` | UTC. |
| `exit_timestamp` | `datetime` | UTC. Must be `> entry_timestamp`. |
| `entry_price` | `float` | `> 0`. |
| `exit_price` | `float` | `> 0`. |
| `quantity` | `int` | `>= 1`. Whole shares, matching `OrderIntent.quantity`. |
| `pnl` | `float` | Dollar profit/loss for this trade. May be negative. |
| `pnl_pct` | `float` | `pnl` as a fraction of the entry notional (`entry_price * quantity`). May be negative. |
| `holding_period` | `timedelta` | `exit_timestamp - entry_timestamp`, `> timedelta(0)`. Stored explicitly (not left for a consumer to recompute) so it can be compared directly against the `StrategyDecision.expected_holding_period` that opened the trade — the exact comparison Milestone 9's Adaptive Learning needs. |

## Required fields — `EquityPoint`

One point on the equity curve.

| Field | Type | Guarantee |
|---|---|---|
| `timestamp` | `datetime` | UTC. |
| `equity` | `float` | `>= 0.0`. |

## Required fields — `ReplayRun`

Reproducibility metadata identifying exactly what produced a
`BacktestResult` — added during contract review, before implementation
began, specifically so a regression discovered later can be traced back
to its cause rather than merely re-detected.

| Field | Type | Guarantee |
|---|---|---|
| `run_id` | `str` | Non-empty. A caller-assigned identifier for this specific run — how it's generated (a UUID, a deterministic hash of the run's inputs) is implementation detail, not fixed here. |
| `dataset` | `str` | Non-empty. Which historical dataset was replayed (e.g. `"SPY-daily-2024"`) — plain-language, matching the precedent `benchmarks/*.json`'s own `dataset` field already established, not a path or a hash. |
| `pipeline_versions` | `Mapping[str, str]` | Every contract-shape version this run actually depended on (e.g. `{"features": "2", "hmm_model": "spy_v3", "risk": "1", "execution": "1"}`) — **no guaranteed keys**, since which packages a given run touches is itself implementation detail this freeze doesn't fix. |
| `git_commit` | `str` | Non-empty. The commit hash the code was at when this run was executed. |
| `timestamp` | `datetime` | UTC. When the replay was invoked — distinct from `BacktestResult.generated_at` (when the finished result object was constructed); the two are typically close but not required to be identical, since a long replay can take real wall-clock time between the two. |

All four types (`BacktestResult`, `TradeRecord`, `EquityPoint`,
`ReplayRun`) must be immutable (`frozen=True`) dataclasses, matching
every other contract in this handbook.

## Versioning policy

Follows the same three-tier pattern as
[OrderIntent Contract.md](OrderIntent%20Contract.md#versioning-policy): a
contract-shape version (this document's "Contract history" below) is
independent of whatever internal versioning the eventual backtest engine
defines. Currently **v1** (this freeze, ADR-014).

## Backward compatibility expectations

Same allowed/requires-a-new-ADR/never-permitted structure as
[OrderIntent Contract.md](OrderIntent%20Contract.md#backward-compatibility-expectations).
Notably: adding a new metric field to `BacktestResult` (e.g. a future
"Ulcer Index") is additive and doesn't require a new ADR as long as it
doesn't change the meaning of an existing field; changing `max_drawdown`
or `win_rate`'s bounds, or `trade_log`/`equity_curve`'s ordering
guarantees, would — those orderings are exactly what makes golden-dataset
regression testing meaningful.

## Contract history

- **v1** ([ADR-014](../Architecture/ADR/ADR-014-BacktestResult-Contract.md)):
  initial freeze — `BacktestResult` (`start_date`, `end_date`, `symbols`,
  `initial_equity`, `final_equity`, `cagr`, `sharpe_ratio`,
  `sortino_ratio`, `calmar_ratio`, `max_drawdown`, `win_rate`,
  `profit_factor`, `average_holding_period`, `exposure`, `turnover`,
  `trade_log`, `equity_curve`, `replay_run`, `generated_at`, `metadata`),
  `TradeRecord`, `EquityPoint`, `ReplayRun`. No implementation exists
  yet; this is the contract Milestone 8 is built against, not a retrofit
  onto existing code.

## Enforcement

Not yet mechanically enforced — there is no `backtest.models` module yet
(distinct from the pre-existing, untooled `backtest/` sandbox). The
first implementation ships `tests/backtest/test_models.py` enforcing
every constraint above, plus `tests/contracts/test_backtestresult_contract.py`
verifying the frozen field set, version metadata, and serialization
round-trip — matching every prior contract. Golden-dataset regression
tests (`tests/regression/baseline_results/*.json`, per the technical
lead's explicit recommendation) are a *separate*, additional layer on
top of this contract enforcement: contract tests check the *shape* never
silently breaks, regression tests check the *numbers* a specific,
pinned scenario produces never silently drift.

## Ownership

Build and maintain: [Quant Researcher](../04_QUANT_RESEARCHER.md) (metric
correctness, replay fidelity) jointly with
[QA Engineer](../09_QA_ENGINEER.md) (golden-dataset/regression
methodology, per that role's existing "a backtest result is not accepted
as evidence of anything without a stated out-of-sample methodology and
transaction-cost assumptions" testing standard). Binding on every
consumer: Milestone 9 (Adaptive Learning, evaluating `TradeRecord.
holding_period` against `StrategyDecision.expected_holding_period`) and
[11_DOCUMENTATION_ENGINEER.md](../11_DOCUMENTATION_ENGINEER.md) (model
cards citing backtest performance). A consumer that needs a capability
this contract doesn't provide raises it against this document — it
doesn't reach into `src/backtest/` internals to work around it.
