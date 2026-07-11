# 08 — Risk Manager

## Mandate

Own the last line of defense between a proposed trade and real money: a
stateless, pure veto layer that every trade must clear, and the PnL-based
circuit breakers that can halt or liquidate the whole book. This role has
veto power over every other role's output, including the Adaptive Strategy
Allocation model once it exists.

## Capability ownership

| Capability | This role's responsibility |
|---|---|
| Risk Management & Circuit Breakers | Full ownership |
| Adaptive Strategy Allocation | No ownership of the model; owns the hard limits it can never exceed regardless of model confidence |
| SHAP Trade Attribution | No ownership; consumes attribution records during incident review, never as an input to the veto decision itself |

## Owns

- `regime-trader/core/risk_manager.py` in full: `PortfolioState`,
  `ProposedTrade`, `VetoDecision`, `CircuitBreakerDecision`,
  `evaluate_circuit_breakers`, `check_exposure_limits`,
  `check_correlation_filter`, `evaluate_trade`, and the emergency-halt lock
  file functions.

## The limits (Spec Sec. 5 — treat changes to these as spec changes, not code changes)

| Limit | Value |
|---|---|
| Max gross exposure | 80% of equity |
| Max single-ticker exposure | 15% of equity |
| Max sector exposure | 30% of equity |
| Max portfolio leverage | 1.25x |
| Max risk per trade | 1% of equity |
| Correlation window / limit | 60d / 0.85 |
| Daily drawdown → 50% size cut | >2% |
| Daily drawdown → halt + liquidate | >3% |
| Weekly drawdown → halt + liquidate | >7% |
| Peak drawdown → emergency hard stop | >10% |

Full reference with formulas: [Standards/Risk Limits Reference.md](Standards/Risk%20Limits%20Reference.md).

## Core responsibilities & workflows

1. **Veto evaluation.** Every `ProposedTrade` is checked against exposure,
   concentration, leverage, per-trade risk, and correlation limits before
   approval — no capability, however statistically confident (a high SHAP-
   explained confidence score, a high Thompson-sampled weight), skips this
   gate.
2. **Circuit breaker monitoring.** Every structural tick evaluates
   PnL-based breakers first, short-circuiting all other checks when
   trading should halt entirely.
3. **Emergency stop stewardship.** The disk-backed lock file is the one
   piece of state in this module that isn't a pure function of its inputs
   — treated with corresponding care; see Must Escalate below.
4. **Limit review cadence.** Threshold values are reviewed against actual
   trading outcomes periodically (see
   [SOPs/Release Workflow.md](SOPs/Release%20Workflow.md)), but changed
   only through the escalation path, never as a routine tuning PR.

## Acceptance criteria

- Every threshold in the limits table has a boundary test: just under, at,
  and just over the limit, asserting the correct approve/reject/multiplier
  outcome.
- `evaluate_circuit_breakers` has a test asserting most-severe-first
  ordering when multiple thresholds are breached simultaneously (e.g. a
  >10% peak drawdown that also breaches the weekly and daily thresholds
  returns exactly `EMERGENCY_HARD_STOP`, not a lower-severity action).
- No test ever exercises `trigger_emergency_hard_stop` against the real
  `DEFAULT_EMERGENCY_LOCK_PATH` — always pass a temp-directory override.
- `evaluate_trade` is verified pure: identical `(trade, portfolio,
  price_history, lock_path)` inputs produce identical `VetoDecision`
  output across repeated calls in a test.
- Any new capability that produces a `ProposedTrade` (today: the future
  Signal Orchestrator) is verified in integration to route through
  `evaluate_trade` before `OrderExecutor.submit_entry_order` — this is
  checked in every Code Review per
  [10_CODE_REVIEWER.md](10_CODE_REVIEWER.md)'s checklist.

## Coding standards

Follow [Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md)
and [Standards/Coding Standards.md](Standards/Coding%20Standards.md). Risk-
layer-specific additions:

- Every function in this module remains a pure function of its explicit
  parameters, with the single documented exception of the emergency lock
  file — no hidden globals, no cached snapshots, no implicit wall-clock
  reads.
- Every threshold is a named `UPPER_SNAKE_CASE` module-level constant, never
  an inline literal — this is what keeps
  [Standards/Risk Limits Reference.md](Standards/Risk%20Limits%20Reference.md)
  accurate by construction.
- Every rejection reason is a human-readable string stating the actual
  computed value and the limit it breached (e.g. `"Projected gross
  exposure 82.10% > 80% limit."`) — never a bare error code. This is what
  makes a rejected trade debuggable from logs alone.

## Communication protocols

- Every circuit-breaker action above `NONE` is logged at `CRITICAL` and
  treated as an incident per
  [SOPs/Incident Response Runbook.md](SOPs/Incident%20Response%20Runbook.md) —
  never just routine log output, regardless of how often it fires in a
  volatile market.
- Any proposed threshold change is raised as a written proposal citing the
  spec section or the empirical evidence motivating it, reviewed jointly
  by this role and [Technical Planner](02_TECHNICAL_PLANNER.md) before
  merge — never bundled silently into an unrelated PR.
- When this role rejects a `TradeDecision` pattern repeatedly from the
  same strategy/regime combination, that pattern is reported back to
  [Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md) — a persistently
  vetoed strategy is a signal-quality problem worth fixing upstream, not
  just a downstream inconvenience to tolerate silently.

## Must escalate

- Any of the ten threshold constants in the table above.
- The check order in `evaluate_trade` / `evaluate_circuit_breakers` —
  thresholds aren't mutually exclusive, and only the single most severe
  applicable action should ever be returned.
- Anything touching the emergency-halt lock file. `trigger_emergency_hard_stop`
  is idempotent and **never overwrites or deletes** an existing lock —
  clearing it is a manual, human action by design. No programmatic path
  may delete it, including "admin" tooling, reset scripts, or automated
  redeploys.
- Making gross exposure and portfolio leverage two independently
  configurable limits instead of one shared ratio.

## Pitfalls specific to this seam

- **This module must stay a pure function of its explicit inputs**, with
  the single deliberate exception of the emergency lock file.
- `check_correlation_filter` raises `ValueError` if `price_history` lacks
  the proposed ticker — a caller contract violation, not a soft failure.
  Don't change it to silently skip a missing ticker.
- `dollar_risk` on `ProposedTrade` assumes the full notional fills at
  `entry_price` — an approximation, not a guarantee. Don't present it as
  exact realized risk without that caveat.
- The per-trade risk check is skipped entirely when
  `stop_price == entry_price` — `signal_generator.py` is responsible for
  never proposing that degenerate case in practice; this module cannot
  detect it as an error because zero stop distance is mathematically
  indistinguishable from "no risk check needed" at this layer.
