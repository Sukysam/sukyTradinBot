# ADR-015: Backtesting Engine Design

**Status**: Accepted
**Date**: 2026-07-13
**Milestone**: [8 — Backtesting & Validation](../../../../PROJECT_STATUS.md)

## Context

Milestone 8 built `src/backtest/`: the first real consumer of the
frozen `OrderIntent` contract (and, transitively, every contract before
it), replaying historical bars through the *entire* decision pipeline
and producing a `BacktestResult`. Its charter is narrow and explicit:
prove the pipeline behaves deterministically under replay, simulate
fills, track a portfolio, and compute performance metrics — never
retrain a model. This record covers the implementation decisions behind
it, all made *after* `BacktestResult` itself was already frozen
([ADR-014](ADR-014-BacktestResult-Contract.md)).

Unlike Milestones 6 and 7, no legacy module exists to ground this one
in — `regime-trader/`'s `TradeDecision` already arrived with prices
pre-computed by the never-built `signal_generator.py` (see
[Known Gaps.md](../Known%20Gaps.md) item 4), so there is no prior
backtest engine that ever exercised the full HMM → strategy → risk →
execution chain together. Every decision below is a first attempt, not
a port.

---

## Decision 1: Two build phases — deterministic replay first, metrics second — per explicit instruction

**Status**: Accepted

### Context

The technical lead's guidance for this milestone was explicit: "This is
the first milestone where I would not build everything at once. Phase
A: replay only... prove the pipeline is deterministic. Phase B: trade
log → portfolio → metrics → BacktestResult."

### Decision

`backtest.replay.run_replay` (Phase A) produces a `ReplayResult`
(`trade_log`, `equity_curve`) with no metrics computation and no
`BacktestResult` construction. Determinism was verified
(`tests/backtest/test_replay.py::TestDeterminism`, two identical runs
producing byte-identical output) *before* `backtest.metrics` or
`backtest.engine` were written at all. `BacktestEngine` (Phase B) is a
thin layer on top: it calls `run_replay`, then `compute_metrics`, then
assembles the frozen `BacktestResult`.

### Consequences

- A bug in replay determinism would have been caught immediately,
  isolated from any metric-computation code, rather than surfacing
  later as "why don't my Sharpe ratios match" with two possible fault
  layers to search.
- `ReplayResult` is a genuinely useful intermediate artifact on its own
  — a caller wanting only a trade log (no metrics) can call `run_replay`
  directly.

### Alternatives Considered

- **Build `BacktestEngine.run` as one unbroken pipeline from the
  start** — rejected per explicit instruction; also would have made the
  determinism property (Decision 1's whole point) harder to isolate and
  verify independently of metric-computation bugs.

---

## Decision 2: Fills happen at the bar's own open — the causal boundary for look-ahead

**Status**: Accepted

### Context

Invariant #1 ("no look-ahead, ever") is this platform's single most
important rule. A backtest is exactly where a look-ahead bug is easiest
to introduce invisibly: using a bar's own close to both make a decision
and fill an order silently assumes information available only at the
end of the bar was available at its start.

### Decision

At replay step `t` (bar `bars[t]`), every decision (features, regime,
strategy, risk) is computed using feature vectors derived only from bars
`< t`. The resulting `OrderIntent`, if any, fills at `bars[t].open` —
the first real price after the information the decision was based on.
Equity is marked at `bars[t].close`, *after* that step's fills — a
separate, standard "mark at close" convention distinct from "fill at
open."

### Consequences

- `execution.models.ExecutionContext.reference_price` at step `t` is
  `bars[t-1].close` (the last known price before the decision), matching
  exactly what `execution.providers.BarSnapshotProvider` would return in
  a live system if "now" were `bars[t].timestamp` — the backtest
  causally mirrors the live system's information boundary by
  construction, not by a separately-maintained parallel rule.
- `backtest.interfaces.FillModel` makes this swappable:
  `NextBarOpenFillModel` (the only implementation shipped) fills at open
  with zero slippage; a future slippage-aware model can be substituted
  without touching `replay.py`.

### Alternatives Considered

- **Fill at the same bar's close (the bar the decision was based on)** —
  rejected outright: this is the textbook look-ahead bug invariant #1
  exists to prevent, using the very close price that made the decision
  attractive to also execute at it.

---

## Decision 3: `PortfolioEngine` is a separate, mutable, stateful class — not folded into `replay.py`

**Status**: Accepted

### Context

The technical lead's guidance: "Don't calculate metrics inside the
replay engine... that separation will let you reuse the portfolio logic
for paper trading later."

### Decision

`backtest.portfolio.PortfolioEngine` owns cash, open positions
(`OpenPosition`, weighted-average cost basis on top-ups), and
day/week/peak equity markers, independent of `replay.py`'s pipeline
orchestration. It is the only genuinely mutable class this milestone
introduces — a deliberate departure from the "prefer frozen value
objects" convention every other contract in this handbook follows,
justified because it holds real state across many replay steps (Master
Charter Section 10: "reach for a class only when there is genuine state
to hold across calls").

### Consequences

- `PortfolioEngine` has no dependency on `FeaturePipeline`, `RegimeService`,
  or any decision-pipeline component — it only knows about fills
  (`open_or_add`/`reduce_or_close`) and mark-to-market prices. A future
  paper-trading module can reuse it directly.
- Tested in complete isolation (`tests/backtest/test_portfolio.py`) with
  no HMM training or feature computation involved — fast, focused unit
  tests for what is otherwise the hardest-to-verify-by-eye part of the
  engine (weighted-average cost basis, partial-exit accounting).

### Alternatives Considered

- **A frozen `PortfolioState`-only design, rebuilding a new snapshot each
  step from an external ledger** — rejected: `risk.models.PortfolioState`
  already is that frozen snapshot type, consumed once per step;
  `PortfolioEngine` is the mutable *producer* of it, not a replacement.

---

## Decision 4: Multi-symbol replay is lockstep and requires aligned timestamps

**Status**: Accepted

### Context

Portfolio-level risk checks (`GrossExposureValidator`, sector
concentration) need every symbol's current position and price
*together* at one point in time — not one symbol's entire history
replayed before the next begins.

### Decision

`replay.run_replay` processes every symbol at each shared timestamp
before advancing to the next timestamp. `_aligned_timestamps` requires
every symbol's bar series to have exactly the same timestamps;
`InsufficientReplayHistoryError` otherwise.

### Consequences

- Portfolio-level risk validators see accurate, simultaneous state for
  every symbol — no risk of one symbol's stale position data leaking
  into another's decision.
- Trade-off, accepted: this milestone cannot replay symbols with
  different trading calendars (different exchanges, different listing
  dates) in one run. A future milestone building genuine calendar
  alignment (forward-filling, explicit non-trading-day handling) would
  need to extend `_aligned_timestamps`, not work around it silently.

### Alternatives Considered

- **Per-symbol independent replay, merged only for reporting** —
  rejected: makes portfolio-level risk checks (gross exposure, sector
  caps) meaningless, since no single point in the replay would have a
  true cross-symbol portfolio snapshot to check them against.

---

## Decision 5: Metrics grouped into `returns`/`risk`/`exposure`/`trade_quality` — per explicit instruction

**Status**: Accepted

### Decision

`backtest.metrics` is a subpackage, not one large module: `returns.py`
(`cagr`, `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`), `risk.py`
(`max_drawdown`), `exposure.py` (`exposure`, `turnover`),
`trade_quality.py` (`win_rate`, `profit_factor`,
`average_holding_period`). `compute_metrics` in `metrics/__init__.py` is
the one aggregating entry point `engine.py` calls.

### Consequences

- Each module is independently testable and small (`tests/backtest/
  test_metrics.py` has one test class per function, not per module).
- Degenerate-denominator cases (`calmar_ratio`, `profit_factor`) return
  `float("inf")`, matching `risk.models.PortfolioState.gross_exposure_pct`'s
  existing convention — documented per-function, not just in the
  Standards doc.
- `sharpe_ratio`/`sortino_ratio` return `0.0` (not `inf`) for a
  zero-variance equity curve — a deliberate, narrower convention than
  `calmar_ratio`/`profit_factor`'s, since this codebase has no precedent
  for an "infinitely good" Sharpe and a flat curve reads more honestly
  as "no signal" than "perfect."

---

## Decision 6: `equity_curve` is seeded with a pre-replay point equal to `initial_equity`

**Status**: Accepted

### Context

`BacktestResult.equity_curve[0].equity == initial_equity` is a frozen
invariant (ADR-014). A naive replay recording only post-fill,
marked-at-close equity would violate this the moment a trade fills on
the very first replayed bar (`equity_curve[0]` would already reflect
that fill).

### Decision

`run_replay` seeds `equity_curve` with one point *before* the loop
starts: `timestamp = bars[replay_start_index - 1].timestamp` (the close
of the last warm-up bar), `equity = initial_equity` (no fills have
happened yet). Every subsequent point is the normal per-step,
marked-at-close value.

### Consequences

- `BacktestResult`'s own contract invariant holds unconditionally,
  verified by `tests/backtest/test_replay.py::TestReplayBasics::
  test_equity_curve_starts_at_initial_equity`, not merely assumed.
- One real bug caught during implementation: the first draft of this
  milestone did not seed this point and failed `BacktestResult`'s
  invariant on the very first end-to-end smoke test that happened to
  trade on day one.

---

## Decision 7: `git_commit` and `pipeline_versions` are explicit inputs, not internal side effects

**Status**: Accepted

### Context

`ReplayRun` (ADR-014 Decision 5) needs a `git_commit`. Shelling out to
`git` from inside `BacktestEngine.run` would work, but silently gives
the engine an external process dependency and a hidden failure mode.

### Decision

`git_commit` is a required keyword argument to `BacktestEngine.run` —
the caller supplies it. `backtest.engine.current_git_commit()` is a
separate, explicit, opt-in helper a caller can invoke to obtain one; it
is never called implicitly. Matches [Coding Standards](../../Standards/Coding%20Standards.md)'s
"dependency injection over hidden construction."

### Consequences

- `BacktestEngine.run` is fully testable without a git repository
  present or any subprocess call — every test in `tests/backtest/
  test_engine.py` passes a literal string.
- `current_git_commit()` raises `BacktestError` (never returns a
  placeholder like `"unknown"`) when `git` is unavailable — a
  `ReplayRun` with a fabricated commit hash would defeat the entire
  point of the field.

---

## Decision 8: Golden-dataset regression uses documented tolerance, not exact equality

**Status**: Accepted

### Context

The technical lead's instruction: "every CI run should reproduce: same
trades, same equity curve, same summary metrics within documented
tolerances." This project's own CI matrix runs Python 3.9 and 3.11
against different resolved `numpy`/`scipy` versions (a real, previously
observed source of behavioral difference — see the mypy fix in
Milestone 5's numpy-version-dependent type inference). `hmmlearn`'s EM
training is not guaranteed bit-identical across BLAS/LAPACK backends.

### Decision

`tests/regression/test_golden_dataset.py` compares a fresh run of the
canonical synthetic scenario (`tests/regression/golden_dataset.py`)
against a checked-in baseline
(`tests/regression/baseline_results/synthetic_daily_2024.json`):
structural properties (trade count, equity-curve length, symbol, side)
compared exactly; every float (`entry_price`, `exit_price`,
`final_equity`, every summary metric) compared with `pytest.approx(rel=
1e-3)`.

### Consequences

- The regression suite is meaningful (catches a real behavioral
  regression) without being flaky across the CI matrix's two Python/numpy
  combinations.
- Named `SYNTH`, not `SPY` — this repository has no live market-data
  credentials (Known Gaps), so, like every other test fixture in this
  codebase, the "golden dataset" is deterministic synthetic data, never
  real historical SPY prices. Documented explicitly in `golden_dataset.py`'s
  own docstring so a future reader never mistakes it for real data.

### Alternatives Considered

- **Exact equality** — rejected per the reasoning above: a real risk of
  CI flakiness across the Python 3.9/3.11 matrix, not a hypothetical one.
- **Use real SPY data** — rejected: no live market-data credentials
  exist in this environment (see Architecture/Known Gaps.md); using real
  data would also make the baseline non-reproducible by anyone without
  the same historical snapshot.

---

## Deliberately deferred

- **Multi-symbol correlation-aware position sizing beyond what
  `risk.RiskService` already provides.** This milestone replays whatever
  the existing pipeline decides; it doesn't add new cross-symbol logic.
- **Slippage/partial-fill models beyond `NextBarOpenFillModel`.** The
  `FillModel` Protocol exists specifically so one can be added later
  without touching `replay.py`.
- **Live paper-trading reuse of `PortfolioEngine`.** Decision 3 makes it
  possible; actually wiring it into a paper-trading loop is future work.
- **A real per-venue tick-size table, live bid/ask, `LIMIT` orders** —
  already deferred at the `execution` layer (ADR-013); this milestone
  inherits those gaps unchanged, since it consumes `execution` as-is.
