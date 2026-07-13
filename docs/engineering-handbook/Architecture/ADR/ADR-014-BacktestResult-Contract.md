# ADR-014: Freeze the BacktestResult Contract

**Status**: Accepted
**Date**: 2026-07-13
**Milestone**: [8 — Backtesting & Validation](../../../../PROJECT_STATUS.md) (contract only —
no implementation in this record; see Context)

## Context

Every milestone since 4 has frozen its output contract before the
package producing it existed. Milestone 8 continues that discipline:
`src/backtest/` does not exist yet. `BacktestResult` is frozen first.

Unlike `RegimeState`/`StrategyDecision`/`ExecutionDecision`/`OrderIntent`
— all single-event snapshots — `BacktestResult` is a **run-level
summary**: the output of replaying potentially years of historical bars
through the entire decision pipeline (Market Data → Features → HMM →
Strategy → Risk → Execution) and simulating fills. This is the first
contract in this handbook shaped like an aggregate report rather than a
point-in-time decision, and that difference drives every decision below.

The pre-existing `backtest/` directory (a crypto SMA-crossover sandbox)
is explicitly out of scope as a grounding source —
[00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md) Section 1 already
designates it lower-stakes and separate, and its `sma_crossover.py::
backtest` function returns an undocumented `dict`, not a contract. This
freeze borrows a handful of that sandbox's field *names* (`win_rate`,
`max_drawdown`) for consistency, not its shape or logic.

## Decision

`backtest.models.BacktestResult` — 18 fields covering run identification
(`start_date`, `end_date`, `symbols`, `initial_equity`, `final_equity`),
ten performance metrics (`cagr`, `sharpe_ratio`, `sortino_ratio`,
`calmar_ratio`, `max_drawdown`, `win_rate`, `profit_factor`,
`average_holding_period`, `exposure`, `turnover`), two embedded
record-list types (`trade_log: tuple[TradeRecord, ...]`,
`equity_curve: tuple[EquityPoint, ...]`), plus `generated_at` and
`metadata` — is frozen as a binding contract, documented in full at
[Standards/BacktestResult Contract.md](../../Standards/BacktestResult%20Contract.md),
*before* `src/backtest/` is scaffolded.

1. **The equity curve and trade log are part of the frozen contract,
   not left as internal implementation detail.** This is a deliberate
   departure from Milestone 7's `ExecutionContext`/`FeatureSnapshot`
   precedent (deliberately *unfrozen*, since they carry transient market
   observations). `trade_log`/`equity_curve` are the opposite case:
   they're exactly what `reporting.py` needs to render anything, and
   exactly what a golden-dataset regression test needs to compare
   run-to-run. Freezing their shape is what makes "did this commit
   change the backtest's numbers" a well-defined question.
2. **`TradeRecord` carries `strategy_id`/`regime_id`/`holding_period`
   explicitly**, not left for a consumer to derive. This gives Milestone
   9 (Adaptive Learning) exactly what it needs to compare a closed
   trade's realized `holding_period` against the `StrategyDecision.
   expected_holding_period` that opened it — the comparison
   `StrategyDecision Contract.md` named as the reason
   `expected_holding_period` exists in the first place (ADR-008),
   finally reachable three milestones later.
3. **Degenerate ratios (`calmar_ratio`, `profit_factor`) are `float
   ("inf")`, never a fabricated large number or a `None`.** Grounded in
   an existing convention already in this codebase —
   `risk.models.PortfolioState.gross_exposure_pct` already returns `inf`
   for a zero-equity denominator rather than raising or returning a
   sentinel. A backtest with zero drawdown or zero losing trades is a
   real, legitimate (if unusual) outcome, not an error condition.
4. **`side` on `TradeRecord` reuses `execution.models.OrderSide`**
   rather than a new enum — `backtest` depends on `execution` at import
   time for this one type, the same way `hmm` depends on `features` for
   `FeatureVector`.

## Consequences

- Whoever implements Milestone 8 has one document to build against
  before writing `src/backtest/`'s first line — fill simulation,
  replay mechanics, and intermediate portfolio tracking are all free to
  be designed, because none of that is what this freeze constrains.
- Golden-dataset regression tests (`tests/regression/baseline_results/
  *.json`, per the technical lead's explicit recommendation) have a
  stable, versioned shape to serialize against from day one — they don't
  need to be redesigned if the backtest engine's internals change later.
- `BacktestResult` has more required fields (18, plus two embedded
  record types) than any prior contract in this handbook. This is not
  scope creep: a run-level summary genuinely carries more information
  than a single decision does, and each field is independently
  justified in the Standards doc.
- Trade-off, accepted: because no implementation exists yet, this freeze
  is more speculative than a freeze written against real code — same
  acknowledgment every prior "freeze before implementation" ADR in this
  handbook has made. `metadata`'s empty guaranteed-key set is the same
  hedge here.
- Trade-off, accepted: fill-simulation realism (slippage, partial fills,
  whether `OrderIntent.reference_price` is treated as an achievable
  fill price) is entirely unconstrained by this freeze. A backtest that
  assumes perfect fills at `reference_price` will overstate performance
  relative to reality — a known, documented risk for whoever builds the
  engine to address explicitly, not something this contract can enforce
  structurally.

## Alternatives Considered

- **Keep `trade_log`/`equity_curve` as separate, unfrozen return values
  alongside a lean `BacktestResult` of just summary scalars** — rejected:
  splits one logical result across multiple return values with no
  single contract governing them together, and specifically defeats
  golden-dataset regression testing, which needs the full curve/log to
  compare, not just the summary statistics computed from it.
- **A nested `BacktestMetrics` sub-object holding the ten performance
  fields, rather than flattening them onto `BacktestResult` directly** —
  considered for extensibility, not adopted: every other contract in
  this handbook (`StrategyDecision`, `ExecutionDecision`, `OrderIntent`)
  is flat: fields live directly on the top-level dataclass. Introducing
  a new nesting convention for this one contract would be inconsistent
  with the rest of the handbook for a benefit (avoiding a top-level
  field-count bump on a future metric addition) that additive
  backward-compatibility already covers.
- **Represent `profit_factor`/`calmar_ratio`'s degenerate case as `None`
  instead of `float("inf")`** — rejected: `None` would force every
  consumer to handle two return types (`float | None`) for what is
  mathematically a well-defined limit, and this codebase already has a
  precedent (`PortfolioState.gross_exposure_pct`) for using `inf`
  instead.
