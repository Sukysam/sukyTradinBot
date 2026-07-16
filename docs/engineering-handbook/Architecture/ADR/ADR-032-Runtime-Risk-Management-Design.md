# ADR-032: Runtime Risk Management Design (Phase F)

**Status**: Accepted
**Date**: 2026-07-16
**Milestone**: Post-`v2.0.0` continuous evolution — Trading Validation / Runtime, Phase F

## Context

Phase E (ADR-031) proved the runtime can arbitrate a strategy call
against advisory input and emit a `FinalDecision`. Per direct
instruction, Phase F stays intentionally narrow: `FinalDecision ->
RiskService -> ExecutionDecision`, and stop there — **no broker
calls, no order submission**. The runtime must remain completely
paper-safe through this phase; Phase G (paper execution) is a
separate, later, explicitly authorized decision.

`risk.service.RiskService.decide(decision: StrategyDecision, portfolio:
PortfolioState, account: AccountState) -> ExecutionDecision` takes a
`StrategyDecision`, not a `FinalDecision` — and this gap is not an
oversight. `orchestration/__init__.py`'s own module docstring states
it explicitly: *"Wiring `FinalDecision` into `risk.RiskService` is not
authorized by this milestone."* That sentence was written during
Milestone 11 and has stood, unresolved, ever since. The direct
instruction to build Phase F this way — `FinalDecision -> RiskService`
— **is that authorization.** This ADR is where it gets exercised.

## Decision

### 1. `_effective_strategy_decision`: the `FinalDecision` -> `StrategyDecision` bridge

`RuntimeFrame` already carries both the original `strategy_decision`
(pre-arbitration) and the `final_decision` (Phase E's arbitrated
outcome) by the time it reaches `RiskEmitter`. `RiskService.decide`
needs a `StrategyDecision`-shaped input, and `FinalDecision` itself
has no `expected_holding_period`/`metadata` to build one from scratch.
The bridge is `dataclasses.replace(strategy_decision, allocation=
final_decision.final_allocation, confidence=final_decision.confidence,
reasoning=final_decision.rationale)` — every field arbitration can
actually change is overridden on the *original* decision; everything
else (`timestamp`, `symbol`, `strategy_id`, `regime_id`,
`expected_holding_period`, `metadata`) passes through unaffected,
since arbitration never touches those.

This is the one non-obvious design decision in this phase, so it's
worth being explicit about why it's correct: `RiskService.decide`
bounds `approved_allocation` to `[0.0, decision.allocation]`. Passing
the pre-arbitration `strategy_decision` directly (ignoring
`final_decision`) would size risk against the strategy's *original*
ask, silently discarding whatever confirmation, reduction, or
suppression Signal Orchestration decided — making Phase E's entire
existence pointless from Risk's perspective. Passing the *arbitrated*
allocation as the ceiling is the only choice that keeps Phase E's
output meaningful downstream.

### 2. `app.risk_loop.RiskEmitter`: bridge, decide, log, no broker calls

`handle_frame` builds the effective decision (Decision 1), fetches
`portfolio`/`account` from injected providers, calls `RiskService.
decide`, logs one `execution_decision_emitted` event per success
(symbol, timestamp, approved, approved_allocation, decision_type,
latency), records `ops.metrics.MetricsRegistry`'s fifth real
production consumer, and returns the enriched frame. A failure
(`risk.exceptions.RiskError` — in practice only `InvalidSizingResultError`,
since a normal validator rejection just produces `approved=False`,
not a raise) is caught and logged, never propagated. Nothing in this
class or anywhere else in Phase F touches a broker, constructs an
order, or calls `execution.*` — the runtime's last action is logging
an `ExecutionDecision`.

### 3. `portfolio_state_provider`/`account_state_provider`: required, called fresh every frame

Unlike Phase E's optional advisory providers (which have a valid
"nothing to contribute" default), `RiskService.decide` has no graceful
no-portfolio path — every validator/sizing rule reads `portfolio`/
`account` directly. A single snapshot injected once at bootstrap would
also be actively wrong: portfolio equity and buying power change with
every trade and every price move, so a stale snapshot would silently
misprice risk from the first bar after it went stale. Both providers
are therefore required constructor parameters, called fresh on every
`handle_frame`. This runtime has no broker/account-query component of
its own yet (that's Phase G's job), so there is no real default to
construct either — the third distinct "no default" case in this
runtime (after `regime_service`'s missing artifact and
`strategy_registry`'s missing domain mapping), here because the true
value is live, per-account data this phase has no way to fetch on its
own. A provider that raises is caught, logged with a specific event
(`portfolio_state_provider_failed`/`account_state_provider_failed`),
and the frame is dropped (`None`) rather than proceeding with
fabricated portfolio/account state.

### 4. `risk_service` *does* default -- unlike `regime_service`/`strategy_registry`

`build_risk_loop`'s `risk_service: RiskService | None = None` defaults
to `RiskService.default()` when omitted. This is a deliberate contrast
with ADR-029/ADR-030's "no working default" reasoning: `RiskService.
default()` builds a genuinely sensible pipeline (`BuyingPowerValidator`
+ `ExposureCapacitySizing` + `DrawdownCircuitBreaker`) that needs no
trained model and no per-model domain mapping to be meaningful —
`RiskServiceConfig`'s only real knob (`sector_map`) already has a
documented, accepted empty-dict default elsewhere in this codebase.
Unlike a `RegimeService` with no training or a `StrategyRegistry` with
invented regime_id mappings, a default `RiskService` doesn't produce a
misleading result — it produces the platform's own considered default
risk posture.

### 5. `RuntimeFrame.require_*`: centralized field-presence validation

Every emitter's `handle_frame` used to open with its own `if frame.x
is None: raise ValueError(...)` (or, for two-field checks, an `or`
chain). These are replaced with `frame.require_feature_vector()`,
`frame.require_regime_state()`, `frame.require_strategy_decision()`,
`frame.require_final_decision()`, and the new `frame.
require_execution_decision()` — each fully typed (returns the concrete
type, not `Any`), raising the same `ValueError` shape as before.
`RegimeEmitter`, `StrategyEmitter`, and `OrchestrationEmitter` (all
already merged) are retrofitted to use these instead of repeating the
check inline; `RiskEmitter` uses them from the start. Validation logic
now lives in exactly one place (`RuntimeFrame` itself) instead of
being duplicated, slightly differently worded, in every emitter.

### 6. `RuntimeFrame` gains `execution_decision`

Same pattern as every prior field: `execution_decision: ExecutionDecision
| None = None`, `with_execution_decision`, and an enrichment-order
check (`execution_decision` requires `final_decision`).

## Consequences

- `ops.metrics.MetricsRegistry` now has a fifth emitter-level
  production consumer.
- `ops.checks.risk_service_check` (another of Milestone 12's ten
  factories, unused until now) has its first real consumer.
- The runtime now produces a genuine `ExecutionDecision` end to end —
  the full A-F pipeline (`MarketDataLoop -> FeatureVectorEmitter ->
  RegimeEmitter -> StrategyEmitter -> OrchestrationEmitter ->
  RiskEmitter`) is real, tested, and paper-safe by construction (no
  code path in this phase can reach a broker).
- Adding Phase G (paper execution) means writing an `ExecutionEmitter.
  handle_frame` that reads `frame.require_execution_decision()`,
  builds an `OrderIntent` via `execution.order_builder`, and submits it
  through `execution.broker_adapter.AlpacaBrokerAdapter` -- the first
  phase in this runtime where `handle_frame` has a real side effect
  beyond logging/metrics.
- Trade-off, accepted and disclosed: `build_risk_loop` now takes five
  required positional parameters before any keyword-only ones
  (`config`, `regime_service`, `strategy_registry`,
  `portfolio_state_provider`, `account_state_provider`). Each
  represents a genuinely non-fabricatable dependency, so this is an
  accepted consequence of the "extend, don't rewrite" discipline
  rather than an oversight -- but if Phase G adds another
  non-optional, non-defaultable dependency, a small bundled
  `RuntimeDependencies`-style object may be worth introducing then,
  not speculatively now.
- `app.bootstrap.__version__`/`app.__version__` bumped `0.5.0` ->
  `0.6.0`.

## Alternatives Considered

- **Pass `frame.strategy_decision` (pre-arbitration) directly to
  `RiskService.decide`, ignoring `final_decision`** — rejected: this
  is exactly the "not authorized" wiring gap Milestone 11 flagged,
  reintroduced by omission. It would size risk against a ceiling
  Signal Orchestration never actually approved.
- **Extend `risk.models.StrategyDecision` or `RiskService.decide`'s
  signature to accept a `FinalDecision` directly** — rejected: `risk`
  is a frozen-contract package (`ExecutionDecision`, ADR-010); adding
  a new accepted input type to its sanctioned entry point is a
  `risk`-package-level design change, not something this runtime
  ADR should decide unilaterally. The bridge lives entirely in `app`,
  touching no frozen contract.
- **Default `portfolio_state_provider`/`account_state_provider` to a
  fixed snapshot supplied once at bootstrap** — rejected: portfolio/
  account state is inherently live; a fixed snapshot would silently
  go stale after the first trade, misrepresenting risk as favorably
  as the initial snapshot happened to look.
- **Give `RiskEmitter` its own try/except wrapper around the whole
  `handle_frame` body instead of three targeted ones** — rejected:
  the existing per-source try/except blocks (`portfolio_state_provider`,
  `account_state_provider`, `RiskService.decide`) produce a specific,
  actionable log event for each failure mode, matching the precision
  every earlier emitter in this runtime already provides; a single
  catch-all would blur which dependency actually failed.
- **Add a generic `RuntimeFrame.has(field_name: str) -> bool` (string-
  keyed) instead of per-field `require_*` methods** — rejected: a
  string-keyed accessor would need `getattr`/`Any`, losing the static
  typing every other frozen or plumbing type in this codebase
  preserves; explicit `require_*` methods keep full type-checker
  precision at each call site for the same centralization benefit.
