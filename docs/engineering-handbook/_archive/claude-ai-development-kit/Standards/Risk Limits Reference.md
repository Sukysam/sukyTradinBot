# Standard — Risk Limits Reference

Source of truth: `regime-trader/core/risk_manager.py`. Values below are
copied from the module's constants; if the two ever disagree, the code is
authoritative and this file is stale — fix this file, not the other way
around, unless the code itself is the thing being deliberately changed (see
[08_RISK_MANAGER.md](../08_RISK_MANAGER.md)
on why that's an escalation, not a routine edit).

## Exposure / concentration / leverage (`check_exposure_limits`)

| Constant | Value | Formula | Rejects when |
|---|---|---|---|
| `MAX_GROSS_EXPOSURE_PCT` | 80% | `(gross_exposure + new_trade.notional) / equity` | projected ratio > 0.80 |
| `MAX_PORTFOLIO_LEVERAGE` | 1.25x | same ratio as above | projected ratio > 1.25 (never binding while gross cap is 80% < 125%) |
| `MAX_SINGLE_TICKER_PCT` | 15% | `(existing ticker value + new trade.notional) / equity` | projected ratio > 0.15 |
| `MAX_SECTOR_EXPOSURE_PCT` | 30% | `(existing sector value + new trade.notional) / equity` | projected ratio > 0.30 |
| `MAX_RISK_PER_TRADE_PCT` | 1% | `trade.dollar_risk / equity`, where `dollar_risk = quantity * |entry - stop|` | projected ratio > 0.01 — **skipped entirely if `stop_price == entry_price`** |

## Correlation filter (`check_correlation_filter`)

| Constant | Value |
|---|---|
| `CORRELATION_WINDOW_DAYS` | 60 |
| `CORRELATION_LIMIT` | 0.85 |

Rejects a trade if the trailing 60-day Pearson correlation of 1-day log
returns between the proposed ticker and *any* existing position exceeds
0.85. Uses `feature_engineering.log_returns` — the same return computation
the HMM feature matrix uses, so this filter and the HMM never disagree on
what a "return" is.

## Circuit breakers (`evaluate_circuit_breakers`) — most severe first

| Trigger | Threshold | Action | Size multiplier | Liquidate |
|---|---|---|---|---|
| Emergency lock file present | — | `EMERGENCY_HARD_STOP` | 0.0 | yes |
| Peak drawdown | > 10% (`PEAK_DRAWDOWN_EMERGENCY_PCT`) | `EMERGENCY_HARD_STOP` (writes lock file) | 0.0 | yes |
| Weekly drawdown | > 7% (`WEEKLY_DRAWDOWN_HALT_PCT`) | `HALT_WEEK` | 0.0 | yes |
| Daily drawdown | > 3% (`DAILY_DRAWDOWN_HALT_PCT`) | `HALT_DAY` | 0.0 | yes |
| Daily drawdown | > 2% (`DAILY_DRAWDOWN_SIZE_CUT_PCT`) | `CUT_SIZE_50` | 0.5 (`DAILY_DRAWDOWN_SIZE_CUT_MULTIPLIER`) | no |
| none of the above | — | `NONE` | 1.0 | no |

Drawdown definitions (`PortfolioState` properties):
- `daily_drawdown_pct` — vs. `equity_start_of_day` (Alpaca's `last_equity`, prior close).
- `weekly_drawdown_pct` — vs. `equity_start_of_week` (tracked in `EquityTracker`, resets on ISO week change).
- `peak_drawdown_pct` — vs. `equity_peak` (all-time high-water mark, tracked in `EquityTracker`).

Only the single most severe applicable breaker is returned — checks
short-circuit, they are not all evaluated and combined.

## Evaluation order in `evaluate_trade` (the single public entry point)

1. `evaluate_circuit_breakers` — if the result is `EMERGENCY_HARD_STOP`,
   `HALT_DAY`, or `HALT_WEEK`, reject immediately with `size_multiplier=0.0`.
   Exposure/correlation checks are never reached in this case.
2. `check_exposure_limits` + `check_correlation_filter` — combined list of
   violation reasons; any non-empty list rejects the trade.
3. If both pass, approve with `size_multiplier` inherited from the circuit
   breaker result (1.0 normally, 0.5 under a daily size-cut).

## Emergency hard stop lock file

- Default path: `risk_manager.EMERGENCY_HALT.lock` (relative to process cwd
  — see [12_DEVOPS_ENGINEER.md](../12_DEVOPS_ENGINEER.md)
  on why cwd matters here).
- `trigger_emergency_hard_stop` is idempotent: never overwrites or deletes
  an existing lock.
- `is_emergency_halted` is a pure existence check.
- Clearing it is a manual, human-only action. No code path in this
  repository is permitted to delete it programmatically.
