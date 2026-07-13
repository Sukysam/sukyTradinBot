# ADR-011: Risk Manager Design

**Status**: Accepted
**Date**: 2026-07-13
**Milestone**: [6 — Risk Management](../../../../PROJECT_STATUS.md)

## Context

Milestone 6 built `src/risk/`: the first real consumer of the frozen
`StrategyDecision` contract, converting it (with a `PortfolioState`/
`AccountState` snapshot) into an `ExecutionDecision`. Its charter is
narrow and explicit — is this trade allowed, and at what size — nothing
about broker connectivity, order type, or fill handling. This record
covers the implementation decisions behind it, all made *after*
`ExecutionDecision` itself was already frozen ([ADR-010](ADR-010-ExecutionDecision-Contract.md)) —
every decision here is explicitly implementation, not contract, per that
ADR's own "freeze interfaces, not implementation" framing.

Unlike Milestones 4 and 5, this milestone is a packaging job, not a
greenfield build: `regime-trader/core/risk_manager.py` already implements
a real, tested veto layer (`VetoDecision`, `CircuitBreakerDecision`,
`evaluate_trade`, `evaluate_circuit_breakers`) against the limits in
[Standards/Risk Limits Reference.md](../../Standards/Risk%20Limits%20Reference.md).
Every decision below is measured against that existing implementation —
what was ported as-is, what was deliberately changed, and why.

---

## Decision 1: `RiskService.default()` favors graceful reduction over hard rejection for exposure/concentration limits — a real bug found via testing

**Status**: Accepted

### Context

The first implementation wired every ported validator
(`GrossExposureValidator`, `LeverageValidator`,
`SingleTickerExposureValidator`, `SectorExposureValidator`,
`BuyingPowerValidator`) into `RiskService.default()` alongside
`ExposureCapacitySizing` — a new `SizingRule` that reduces (never
rejects) a decision to fit within remaining headroom under those same
four caps. Writing the test suite exposed the problem immediately: a
decision requesting more than the available headroom under, say, the
gross-exposure cap would *always* be caught by `GrossExposureValidator`
first (both check the identical ratio against the identical threshold),
rejecting the decision outright before `ExposureCapacitySizing` ever ran.
The `DecisionType.REDUCED` path was structurally unreachable in the
default pipeline — every test written to exercise it instead produced a
`REJECTED` decision.

### Decision

`RiskService.default()` wires only `BuyingPowerValidator` as a validator
— a concern this milestone treats as a genuine yes/no, not something to
partially fit — and relies on `ExposureCapacitySizing` alone to handle
gross exposure, single-ticker concentration, and sector concentration via
graceful reduction. `GrossExposureValidator`, `LeverageValidator`,
`SingleTickerExposureValidator`, and `SectorExposureValidator` remain
fully implemented and tested, but are excluded from the default
composition; a caller wanting the legacy module's original zero-tolerance
behavior (reject outright rather than reduce) constructs `RiskService`
directly with them instead of calling `.default()`.

### Consequences

- The default policy is more permissive than `core/risk_manager.py`'s:
  a decision that would have been rejected outright by the legacy module
  now executes at whatever reduced size actually fits. This is a
  deliberate product decision, not an accidental relaxation — see
  Alternatives Considered for why it was kept rather than reverted.
- `tests/risk/test_service.py::TestRejectionPath::
  test_gross_exposure_violation_rejects_under_a_strict_validator_policy`
  and `TestMultipleSimultaneousViolations` explicitly construct a
  `RiskService` with every validator wired in, demonstrating the
  zero-tolerance policy is still fully available and tested — this
  milestone doesn't delete that capability, it just isn't the default.
- Same lesson as [ADR-009](ADR-009-Strategy-Engine-Design.md) Decision 2:
  a check that looks like harmless extra safety (a validator at the same
  threshold a sizing rule already enforces) can silently make an entire
  code path unreachable. The fix there was removing a redundant check
  from `allocate()`; the fix here is not wiring two mechanisms that
  quietly compete for the same concern into the default pipeline
  together.

### Alternatives Considered

- **Keep all five validators plus `ExposureCapacitySizing` in
  `RiskService.default()`, accept that `DecisionType.REDUCED` never
  fires by default** — rejected: shipping a `DecisionType` value that
  structurally cannot occur in the recommended configuration defeats the
  entire point of ADR-010's explicit tri-state classification.
- **Remove `ExposureCapacitySizing` instead, keep the legacy module's
  pure binary-reject behavior** — rejected: this throws away a genuine,
  useful capability (fitting a smaller position rather than rejecting
  a proposal outright) for no benefit beyond matching the legacy
  module's original behavior, which this milestone was never obligated to
  reproduce byte-for-byte (see ADR-010's own "hardened port, not a
  byte-for-byte one" framing, first established for the
  `risk_adjustments`-on-size-cut requirement).
- **Give `ExposureCapacitySizing` and the four exposure validators
  different threshold values (e.g. sizing targets a tighter buffer below
  the hard cap the validators enforce)** — rejected: no such buffer value
  exists anywhere in `Standards/Risk Limits Reference.md`, and inventing
  one would be exactly the kind of unfounded speculative threshold this
  handbook's documentation standards warn against ("distinguish verified
  from reconstructed").

---

## Decision 2: Pipeline order is validators → sizing → circuit breakers, not the legacy module's circuit-breakers-first

**Status**: Accepted

### Context

`core/risk_manager.py::evaluate_trade` checks circuit breakers first and
short-circuits exposure/correlation checks when a breaker is already
halting. The Milestone 6 specification called for the opposite order:
validators, then sizing, then circuit breakers last.

### Decision

`RiskService.decide` follows the specified order. This produces an
identical final `approved`/`approved_allocation` outcome to the legacy
ordering in every case: a halting circuit breaker forces
`approved_allocation` to `0.0` regardless of what validators or sizing
computed first, exactly as it would have if checked first. The only
practical difference is that validators and sizing always run (computing
real, sometimes-discarded `risk_adjustments` reasons) even when a circuit
breaker is about to override everything — a small amount of extra,
harmless computation, not a behavioral difference. Placing the circuit
breaker last also matches its actual role better: it's a final override
authority over any single decision's verdict, not merely an optimization
to avoid wasted work.

### Consequences

- `risk_adjustments` on a circuit-breaker-halted decision can include
  validator/sizing findings that were computed but ultimately irrelevant
  to the final outcome — a fuller audit trail, not a bug. See
  `tests/risk/test_service.py::TestCircuitBreakerActivation::
  test_emergency_halt_overrides_validator_rejection_reasons_too`.
- Trade-off, accepted: marginally more computation per call than the
  legacy short-circuit order. Immaterial in practice — measured latency
  is ~0.026ms/call, see `benchmarks/v0.6-risk-management.json`.

### Alternatives Considered

- **Match the legacy module's circuit-breakers-first short-circuit
  order exactly** — rejected: the specified order was explicit, and
  the two orders are behaviorally equivalent in every outcome that
  matters (see Decision above) — there is no correctness reason to
  deviate from the given specification.

---

## Decision 3: `decision_type` is computed once, then snapped to the exact requested value on a clean approval

**Status**: Accepted

### Context

`ExecutionDecision.__post_init__` (ADR-010) enforces `decision_type`
consistency using strict floating-point comparisons
(`approved_allocation < strategy_reference.allocation`, not an
epsilon-tolerant one). A sizing/circuit-breaker stage that computes an
"unchanged" allocation via `min(allocation, some_other_float)` or
`allocation * 1.0` risks introducing floating-point noise (e.g.
`0.7999999999999999` instead of exactly `0.8`) that would misclassify a
clean approval as `REDUCED`.

### Decision

`RiskService.decide` uses a small internal tolerance (`_TOLERANCE =
1e-9`) only to decide *whether* a stage changed the allocation (and thus
whether to append a `risk_adjustments` note), but when the net effect
across all stages is "unchanged" (within that tolerance), it snaps
`approved_allocation` to `decision.allocation` exactly before
constructing the `ExecutionDecision` — guaranteeing the strict equality
`ExecutionDecision.__post_init__` checks always holds for a genuinely
clean approval. `RiskService` also skips multiplying by a circuit
breaker's `size_multiplier` entirely when that multiplier is `1.0`,
avoiding introducing float noise from a no-op multiplication in the
first place.

### Consequences

- A clean approval is provably classified `DecisionType.APPROVED`, never
  spuriously `REDUCED` due to float representation error — verified by
  `tests/risk/test_service.py::TestApprovalPath::
  test_clean_decision_is_approved_at_full_size`.
- `InvalidSizingResultError` (a `SizingRule` returning more than it was
  given) also uses the same tolerance, so a rule that returns a value
  microscopically larger than its input due to ordinary floating-point
  arithmetic isn't flagged as buggy — only a real, material increase is.

### Alternatives Considered

- **Round `approved_allocation` to a fixed number of decimal places
  instead of snapping to the exact input value** — rejected: rounding
  can itself introduce a value that doesn't exactly equal
  `strategy_reference.allocation` (e.g. rounding `0.1 + 0.2` to 4 places
  gives `0.3000`, which is still not bit-identical to a literal `0.3`
  in IEEE754). Snapping to the known-good original value is exact by
  construction; rounding is not.

---

## Decision 4: `AccountState` is deliberately minimal

**Status**: Accepted

### Context

Unlike `PortfolioState` (ported from `core/risk_manager.py` unchanged),
`AccountState` has no legacy precedent — nothing in `regime-trader/`
models broker-account facts as a distinct type from portfolio state.

### Decision

`AccountState` ships with exactly one field, `buying_power: float` — the
only piece of account-level data any validator in this milestone
consumes. No `cash`, `pattern_day_trader`, or margin fields are added
speculatively.

### Consequences

- Matches [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md)'s Definition
  of Done ("no speculative abstraction for hypothetical future needs").
- Growing `AccountState` for a genuinely new consumer (e.g. a future
  pattern-day-trading rule) is a small, additive, non-breaking change —
  `AccountState` is implementation detail, not part of the frozen
  `ExecutionDecision` contract (see ADR-010's Scope section).

### Alternatives Considered

- **Model a fuller `AccountState` up front (cash, margin, PDT status),
  anticipating Milestone 7's needs** — rejected: no current validator or
  sizing rule needs these fields, and guessing what Milestone 7 will
  actually require risks freezing the wrong shape speculatively — better
  to add fields when a real consumer needs them.

---

## Decision 5: Per-trade dollar risk and the correlation filter are deferred, not ported

**Status**: Accepted

### Context

`core/risk_manager.py::check_exposure_limits` includes a per-trade
dollar-risk check (`dollar_risk = quantity * |entry_price - stop_price|`
against `MAX_RISK_PER_TRADE_PCT`), and `check_correlation_filter` blocks
a trade whose trailing 60-day return correlation with an existing
position exceeds `CORRELATION_LIMIT`. Neither was ported.

### Decision

Both are deliberately left out of `src/risk/` for this milestone.
Per-trade dollar risk needs `entry_price`/`stop_price` — fields that
exist on the legacy `ProposedTrade` but nowhere in `StrategyDecision`
(which carries only an allocation *fraction*, no price information at
all). The correlation filter needs a rolling return history per symbol —
a `price_history: dict[str, pd.Series]` parameter in the legacy function,
with no equivalent among `StrategyDecision`, `PortfolioState`, or
`AccountState`. Building either would mean inventing price/history data
this milestone's actual inputs don't provide, which is not implementable
honestly without a design change to what `RiskService.decide` receives.

### Consequences

- `risk.limits` accordingly does not define `MAX_RISK_PER_TRADE_PCT`,
  `CORRELATION_WINDOW_DAYS`, or `CORRELATION_LIMIT` — only the four
  exposure/leverage constants and the five circuit-breaker constants that
  this milestone's real inputs can actually support.
- Both checks remain real, working code in `core/risk_manager.py` today
  — nothing regresses for the still-live production path; this is a scope
  boundary for `src/risk/`, not a removal of existing protection.
- Whichever milestone first threads real entry/stop prices and/or a
  return-history feed into the risk pipeline (plausibly Milestone 7,
  Execution, which will need real prices for order construction anyway)
  is the natural point to revisit both checks.

### Alternatives Considered

- **Add `entry_price`/`stop_price` fields to `StrategyDecision` retroactively so a per-trade-risk validator has something to check** — rejected: `StrategyDecision` is a frozen contract (ADR-008); widening it to carry pricing information it was never scoped to hold is exactly the kind of contract change that needs its own ADR and explicit sign-off, not something to slip in as a side effect of this milestone's validator coverage.
- **Build `LiquidityValidator` as a working correlation-based check reusing the legacy `check_correlation_filter` logic, renamed** — considered, rejected: this would require inventing a `price_history` input `RiskService.decide`'s signature doesn't have, and "Liquidity" and "correlation with existing positions" are genuinely different concerns being conflated for convenience. `LiquidityValidator` instead ships as an explicit `NotImplementedError` placeholder — see Decision 6.

---

## Decision 6: `LiquidityValidator` is a deliberate `NotImplementedError` placeholder

**Status**: Accepted

### Context

The Milestone 6 validator list named "Liquidity" alongside gross
exposure, sector exposure, leverage, and buying power. No real liquidity
signal (average daily volume, bid-ask spread) exists anywhere in
`StrategyDecision`, `PortfolioState`, or `AccountState`.

### Decision

`LiquidityValidator.validate` raises `NotImplementedError` unconditionally,
with a docstring explaining exactly what data is missing and directing a
future implementer not to register it with `RiskService` until real
market-depth data is available. This follows
[00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md) invariant #4 directly:
"wire in a placeholder that raises `NotImplementedError` on first use...
rather than a stub that quietly no-ops or fabricates a plausible-looking
result" — the same pattern `main.py`'s own `_NotYetImplemented` already
uses elsewhere in this codebase.

### Consequences

- The class exists, is exported, and is tested (`tests/risk/
  test_validators.py::TestLiquidityValidatorPlaceholder`) — a future
  implementer has a concrete extension point, not a TODO comment.
- `RiskService.default()` never wires it in, so `RiskService.decide`
  never raises unexpectedly in normal operation.

### Alternatives Considered

- **Omit the class entirely until real data is available** — rejected:
  a loud, documented placeholder is more useful than no trace of the
  requirement at all — the next implementer sees exactly what's missing
  and why, rather than rediscovering the gap from scratch.

## Verification note

`src/risk/` reaches 100% line and branch coverage — every validator
boundary (just under/at/just over each threshold), every circuit-breaker
tier, the emergency lock file's idempotency, and every
`ExecutionDecision`/`DecisionType` invariant has a dedicated test. Full
suite: 649 tests passing (102 new: 87 in `tests/risk`, 12 in
`tests/contracts/test_executiondecision_contract.py`, 3 added while
closing coverage gaps), ruff/black/mypy clean.
