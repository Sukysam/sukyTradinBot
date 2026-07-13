# ADR-012: Freeze the OrderIntent Contract

**Status**: Accepted
**Date**: 2026-07-13
**Milestone**: [7 — Execution Layer](../../../../PROJECT_STATUS.md) (contract only — no
implementation in this record; see Context)

## Context

ADR-010 established the before-implementation sequencing this record
continues: freeze the next milestone's output type before its package
exists at all, reviewed on its own, implementation only starting
afterward. `src/execution/` does not exist yet. `OrderIntent` is frozen
first.

Unlike `ExecutionDecision`, which is a packaged, hardened port of a real
existing module (`core/risk_manager.py`), `OrderIntent` sits at a genuine
seam: `regime-trader/broker/order_executor.py::OrderExecutor.
submit_entry_order` already does real, tested order construction and
submission — but it takes `entry_price`/`stop_price`/`notional_value` as
direct parameters, sourced (in the legacy system) from `TradeDecision`,
a type that combines what this platform's new architecture deliberately
split across `StrategyDecision` (Milestone 5) and `ExecutionDecision`
(Milestone 6). **Neither of those two contracts carries any price
information at all** — `StrategyDecision.allocation` and `ExecutionDecision.
approved_allocation` are both fractions of allocatable capital, not
dollar amounts or share counts.

This means `OrderIntent` cannot be built from `ExecutionDecision` alone
by a pure function of its fields — building one requires a *live price*
(to convert a fraction into a whole-share quantity) and a *stop-loss
level* that nothing in the current `src/` pipeline computes. The legacy
system derives a stop from "volatility tier" (per `core/risk_manager.py`'s
own comment, referencing Spec Sec. 3) — conceptually available today via
`src/features`'s already-built ATR/volatility features, but no code path
currently threads a `FeatureVector` (or a fresh equivalent) through to
order construction. This ADR freezes `OrderIntent`'s *shape* while being
explicit that sourcing `reference_price` and `stop_loss` is real,
unsolved Milestone 7 implementation work — not glossed over, and not
solved here either, per "freeze interfaces, not implementation."

The user's explicit instruction for this milestone — broker isolation,
with `OrderIntent` deliberately not named `BrokerOrder` — extends
[ADR-002](ADR-002-Market-Data.md)'s adapter-isolation principle
(`alpaca_client.py` as a thin adapter over `src/market_data`, never the
reverse) from market data ingestion to order submission: nothing under
`src/` should import an Alpaca SDK type directly.

**Principle** (added during review, before implementation began — not a
change to the frozen shape above, a statement of why it's shaped this
way): *execution contracts describe trading intent, not market
observations.* `OrderIntent` is durable — its fields describe a decision
that was made and should remain reconstructable and auditable
indefinitely. A live quote, a spread, an ATR reading at build time are
transient — true at the moment `OrderIntent` was built, not a fact worth
freezing into a versioned contract every future consumer must forever
agree on the shape of. This is why `reference_price` is captured as a
plain `float` on `OrderIntent` (the price that was used, a historical
fact worth keeping) while the *mechanism* that produced it — a live
quote, order book depth, an ATR calculation — stays entirely internal to
`src/execution` (see ADR-013's `ExecutionContext`/`FeatureSnapshot`,
deliberately never frozen). The same distinction already implicitly
shaped `StrategyDecision` and `ExecutionDecision`: both work in
allocation *fractions*, precisely so neither has to freeze an opinion
about what a live price is.

## Decision

`execution.models.OrderIntent` — `timestamp`, `symbol`, `side`,
`quantity`, `order_type`, `limit_price`, `time_in_force`,
`reference_price`, `stop_loss`, `take_profit`, `idempotency_key`,
`reasoning`, `execution_reference`, `metadata` — is frozen as a binding
contract, documented in full at
[Standards/OrderIntent Contract.md](../../Standards/OrderIntent%20Contract.md),
*before* `src/execution/` is scaffolded.

1. **Every field type is first-party, never an Alpaca SDK type.** `side`
   (`OrderSide`), `order_type` (`OrderType`), and `time_in_force`
   (`TimeInForce`) are new enums defined in `execution.models`, not
   re-exports of `alpaca.trading.enums`. This is what makes broker
   isolation a structural property, checkable by "does anything under
   `src/` import `alpaca`," rather than a convention someone can
   accidentally violate.
2. **`stop_loss` is mandatory for a `BUY`, forbidden for a `SELL`.** Grounds
   [03_BACKEND_ENGINEER.md](../../03_BACKEND_ENGINEER.md)'s existing
   acceptance criterion ("every entry order carries a mandatory
   stop-loss leg") in the type itself, the same way `ExecutionDecision.
   approved_allocation`'s bound grounds invariant #5. A `SELL` never
   carries one because an exit closes risk rather than needing its own
   protective order.
3. **`idempotency_key` is caller-supplied, never broker-generated.**
   `order_executor.py` today generates a fresh `uuid.uuid4()` per call
   inside the executor itself — meaning a retry of the *same* logical
   order gets a *different* ID, which cannot support genuine idempotent
   retries. `OrderIntent` requires the caller to supply a deterministic
   key instead, so a `BrokerAdapter` retry can safely resubmit the exact
   same `OrderIntent` and rely on the broker's own idempotency handling
   (Alpaca's `client_order_id`) rather than accidentally double-submitting.
4. **`execution_reference` must have `approved is True`.** An
   `OrderIntent` can only ever be built from an approved (full or
   reduced) `ExecutionDecision` — attempting to build one from a rejected
   decision is a caller bug, not a valid state, and fails loudly at
   construction rather than producing a nonsensical order.
5. **No `HOLD` value, no zero-quantity instance.** A decision requiring
   no action (target allocation already matches current position, or
   sizes to fewer than one whole share) produces no `OrderIntent` at all
   — the eventual builder returns `None`. This keeps every real
   `OrderIntent` instance meaningfully submittable by construction,
   rather than requiring every consumer to separately check "is this
   actually an order."

## Consequences

- Whoever implements Milestone 7 has one document to build against
  before writing `src/execution/`'s first line — how buy/sell/hold is
  decided from a target allocation vs. current position, how
  `reference_price` is sourced, and how `stop_loss` is computed are all
  free to be designed, because none of that is what this freeze
  constrains.
- The price-sourcing gap this ADR surfaces (Context) is now a documented,
  visible precondition for Milestone 7's implementation to actually
  produce a real `OrderIntent` — not a surprise discovered mid-milestone.
  A caller cannot construct a valid `OrderIntent` (`stop_loss` required
  for `BUY`) without first solving it, which is the intended forcing
  function: the contract cannot be satisfied by a shortcut that skips
  the stop-loss question.
- Broker isolation becomes checkable, not just documented: a future CI
  check (or a simple `grep`) can assert nothing under `src/` outside a
  `broker_adapter.py`-equivalent module imports `alpaca`.
- Trade-off, accepted: because no implementation exists yet and the
  price-sourcing question is genuinely unresolved, this freeze is more
  speculative than ADR-010's own — same acknowledgment ADR-010 made
  relative to ADR-008. `metadata`'s empty guaranteed-key set is the same
  hedge here.
- Trade-off, accepted: `OrderIntent` has more required fields (13) than
  any prior frozen contract in this handbook. Each is individually
  justified (see Standards doc), but the surface area reflects that an
  order genuinely needs more information than an allocation decision
  does — this isn't scope creep, it's what constructing something
  actually submittable to a broker requires.

## Alternatives Considered

- **Add `reference_price`/`stop_loss` fields to `ExecutionDecision`
  retroactively, so `OrderIntent` could just copy them forward** —
  rejected: `ExecutionDecision` is a frozen contract (ADR-010); widening
  it to carry pricing information it was never scoped to hold needs its
  own ADR and explicit sign-off, not a side effect of designing the next
  milestone's contract. `ExecutionDecision`'s scope (is this trade
  allowed, at what size) is legitimately price-independent — it operates
  on fractions of equity precisely so it doesn't need to know a live
  quote.
- **Have `OrderIntent.stop_loss` remain optional (`float | None`) for
  every side, deferring the mandatory-stop enforcement to `order_builder.
  py` instead of the type itself** — rejected: this is exactly the same
  "documentation vs. enforcement" gap ADR-010 closed for `approved_
  allocation`'s bound and `risk_adjustments`'s non-emptiness. A `BUY`
  `OrderIntent` with no stop-loss should be a structurally invalid state,
  not a runtime check a caller could forget.
- **Name the broker-generated field `client_order_id`, matching
  Alpaca's own terminology** — rejected: `idempotency_key` describes
  what the field is *for* (a broker-agnostic contract's job), not what
  one specific broker calls it — `client_order_id` is exactly the kind
  of broker-specific naming this contract exists to keep out of
  `src/execution/`.
- **Support `LIMIT` orders fully in this freeze, since the type already
  needs to model the choice** — rejected: no current requirement or
  legacy precedent calls for limit orders (`order_executor.py` only ever
  constructs `MarketOrderRequest`). The enum value and `limit_price`
  field exist so the contract doesn't need a breaking change when a real
  need appears, but building the limit-order construction logic itself
  is deferred until a real consumer needs it — the same "freeze the
  interface, not a use nobody has yet" discipline applied elsewhere in
  this handbook.
- **Wait until Milestone 7's implementation exists (including a real
  answer to the price-sourcing question), then freeze the contract
  retroactively** — rejected per the same reasoning ADR-008/ADR-010
  gave: the stricter before-implementation sequencing is the adopted
  process, not a one-off. Freezing the shape now, with the open question
  explicitly documented rather than resolved, is more valuable than
  waiting — it gives whoever builds Milestone 7 a concrete target the
  price-sourcing design must satisfy.
