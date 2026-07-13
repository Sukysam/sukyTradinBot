# Standard — OrderIntent Contract

Governs `execution.models.OrderIntent`, the single output type the
Execution Layer (Milestone 7) is expected to produce. See
[Architecture/ADR/ADR-012-OrderIntent-Contract.md](../Architecture/ADR/ADR-012-OrderIntent-Contract.md)
for why this type is frozen *before* `src/execution/` exists — the same
"freeze interfaces before implementation" discipline
[ADR-010](../Architecture/ADR/ADR-010-ExecutionDecision-Contract.md)
established for `ExecutionDecision`. This document is the binding
contract for whoever implements the Execution Layer against it, and for
every broker adapter that translates an `OrderIntent` into a real API
call.

## Why this exists, and why now

Milestone 7's mandate is narrow on purpose: convert an `ExecutionDecision`
(plus current portfolio state, to determine buy/sell/hold) into a
broker-agnostic description of an order to submit. Nothing about Alpaca
specifically — no `alpaca.trading.enums` types, no client objects, no API
calls — belongs in this contract; that's a `BrokerAdapter`'s job,
consuming `OrderIntent` the same way this milestone consumes
`ExecutionDecision`. This is a deliberate widening of the isolation
principle [ADR-002](../Architecture/ADR/ADR-002-Market-Data.md) already
established for market data (a thin adapter over `src/market_data`, never
the reverse) — nothing under `src/` should import an Alpaca SDK type
directly. Freezing the shape now keeps every module upstream of a broker
adapter (`router.py`, `order_builder.py`, `execution_service.py`)
provably broker-agnostic by construction, not by convention.

This contract is grounded in `regime-trader/broker/order_executor.py`'s
real, tested `OrderExecutor.submit_entry_order` signature and
[03_BACKEND_ENGINEER.md](../03_BACKEND_ENGINEER.md)'s explicit acceptance
criterion that "every entry order carries a mandatory stop-loss leg" —
not designed from a blank page. Where this contract's fields don't map
1:1 onto that legacy signature, that's called out explicitly below and in
ADR-012's Alternatives Considered.

**A real, unresolved gap this freeze surfaces rather than papers over**:
neither `StrategyDecision` nor `ExecutionDecision` carries any price
information — `StrategyDecision.allocation` is a fraction, and
`ExecutionDecision.approved_allocation` is the same fraction, possibly
reduced. `OrderIntent`, by contrast, must carry real prices
(`reference_price`, `stop_loss`) to be submittable at all. Sourcing those
prices — a live quote, and a principled stop-loss level (the legacy
system derives one from "volatility tier," per
`core/risk_manager.py`'s own comment referencing Spec Sec. 3, using
machinery equivalent to `src/features`'s already-built ATR/volatility
features) — is real Milestone 7 implementation work this contract
deliberately does not solve. See ADR-012's Context and Consequences.

## Scope

Applies to `execution.models.OrderIntent` and whatever public method the
eventual `execution.execution_service` module exposes to produce it
(signature not yet fixed — that's implementation, not contract). Does
**not** freeze:

- How a target allocation (from `ExecutionDecision`) is reconciled against
  current position to decide buy/sell/hold, or how much to trade — that's
  `router.py`/`order_builder.py` implementation detail. A decision
  requiring no action produces no `OrderIntent` at all (the builder
  returns `None`), never a degenerate zero-quantity instance — this
  contract has no "hold" value for `side` or a valid zero for `quantity`.
- Where `reference_price` and `stop_loss` actually come from (a live
  quote fetch, an ATR-based stop calculation, or otherwise) — genuinely
  unbuilt machinery today, not fixed by this freeze.
- The shape of `BrokerAdapter` or any broker-specific request/response
  type — implementation detail, deliberately isolated from this contract
  by design (see Why this exists, and why now).
- Retry/idempotency *mechanics* (backoff policy, how many attempts) —
  `OrderIntent.idempotency_key` exists so a retry mechanism *can* be
  built safely, but the mechanism itself is Milestone 7 implementation.

## Required fields

| Field | Type | Guarantee |
|---|---|---|
| `timestamp` | `datetime` | Timezone-aware, normalized to UTC. The `ExecutionDecision.timestamp` this order was built from — the causal "as of" time, not when the `OrderIntent` object was constructed. Must equal `execution_reference.timestamp` (enforced at construction). |
| `symbol` | `str` | Never empty. Must equal `execution_reference.symbol` (enforced at construction). |
| `side` | `OrderSide` (`str, Enum`: `BUY`, `SELL`) | First-party enum — never an Alpaca SDK type. `BUY` opens or adds to a long position; `SELL` reduces or closes one. Never represents opening a short: [00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md) invariant #5 ("every strategy is long-only") applies here exactly as it does to `StrategyDecision.allocation`'s bound — a `SELL` `OrderIntent` is only ever an exit, matching `OrderExecutor`'s existing `liquidate_position` semantics, not a new short entry. |
| `quantity` | `int` | Whole shares, `>= 1`. Never fractional — Alpaca's bracket/OTO orders reject fractional `qty` client-side-unenforced but server-rejected (see `core/risk_manager.py`'s `size_to_shares`, which this contract's eventual builder is expected to reuse the same truncate-down logic from). A decision that sizes to zero whole shares produces no `OrderIntent`, not a `quantity=0` instance. |
| `order_type` | `OrderType` (`str, Enum`: `MARKET`, `LIMIT`) | First-party enum. Only `MARKET` has a real implementation as of this freeze — `LIMIT` is a reserved, documented value for a future implementation, not usable yet. See `limit_price`. |
| `limit_price` | `float \| None` | Required (positive) when `order_type` is `LIMIT`; must be `None` when `order_type` is `MARKET`. |
| `time_in_force` | `TimeInForce` (`str, Enum`: `DAY`, `GTC`) | First-party enum, mirroring the two values `core/risk_manager.py`/`order_executor.py` actually use today. |
| `reference_price` | `float` | Positive. The price `quantity` was sized against and `stop_loss`/`take_profit` are validated relative to — not necessarily the fill price, which is determined by the broker at submission time (especially for a `MARKET` order). |
| `stop_loss` | `float \| None` | **Required (non-`None`) when `side` is `BUY`** — mandatory, per [03_BACKEND_ENGINEER.md](../03_BACKEND_ENGINEER.md)'s existing acceptance criterion ("every entry order carries a mandatory stop-loss leg") and Master Charter's capital-safety-first principle (Section 1). Must be strictly less than `reference_price` for a `BUY`. **Must be `None` when `side` is `SELL`** — an exit closes risk, it doesn't need its own protective stop. |
| `take_profit` | `float \| None` | Optional, always — matches `OrderExecutor.submit_entry_order`'s existing `take_profit_price: float \| None = None`. When present on a `BUY`, must be strictly greater than `reference_price`. Must be `None` when `side` is `SELL`, same reasoning as `stop_loss`. |
| `idempotency_key` | `str` | Never empty. A caller-supplied, deterministic key (not a broker-generated ID) so retrying the *same* logical order intent always produces the *same* key — the precondition for a broker adapter to submit idempotently (Alpaca's own `client_order_id` field exists for exactly this purpose). Never generated by a broker adapter itself (that would make every retry a distinct key, defeating the point). |
| `reasoning` | `str` | Never empty. Human-readable explanation of the order — what was requested, what quantity/side was derived and why. Extends [00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md) invariant #6 one step further downstream than `ExecutionDecision.reasoning`. |
| `execution_reference` | `risk.models.ExecutionDecision` | The exact `ExecutionDecision` this order was built from, embedded in full — full traceability back through `strategy_reference` to the original `StrategyDecision`, without a separate lookup, matching the pattern `ExecutionDecision.strategy_reference` already established. Must have `approved is True` (enforced at construction — an `OrderIntent` is never built from a rejected `ExecutionDecision`). |
| `metadata` | `Mapping[str, Any]` | Free-form. **No guaranteed keys yet** — same reasoning as `ExecutionDecision.metadata` and `StrategyDecision.metadata`: no `src/execution/` implementation exists yet to honestly commit to specific keys. |

`OrderIntent` must be an immutable (`frozen=True`) dataclass, matching
`FeatureVector`, `RegimeState`, `StrategyDecision`, and `ExecutionDecision`.

### Invariants enforced at construction

In addition to the per-field guarantees above, `__post_init__` enforces:

1. `symbol == execution_reference.symbol` and `timestamp == execution_reference.timestamp`.
2. `execution_reference.approved is True`.
3. `quantity >= 1`.
4. `reference_price > 0`.
5. `order_type is LIMIT` implies `limit_price is not None and limit_price > 0`; `order_type is MARKET` implies `limit_price is None`.
6. `side is BUY` implies `stop_loss is not None and stop_loss < reference_price`, and (`take_profit is None or take_profit > reference_price`).
7. `side is SELL` implies `stop_loss is None and take_profit is None`.
8. `idempotency_key` is non-empty after stripping whitespace.
9. `reasoning` is non-empty after stripping whitespace.

## Versioning policy

Follows the same three-tier pattern as
[ExecutionDecision Contract.md](ExecutionDecision%20Contract.md#versioning-policy):
a contract-shape version (this document's own "Contract history" below)
is independent of whatever internal versioning the eventual broker
adapter defines. Currently **v1** (this freeze, ADR-012) — no
implementation exists yet to have driven a v2.

## Backward compatibility expectations

Same allowed/requires-a-new-ADR/never-permitted structure as
[ExecutionDecision Contract.md](ExecutionDecision%20Contract.md#backward-compatibility-expectations),
applied to `OrderIntent`. Notably: adding a new `OrderType` value (e.g. a
real `LIMIT` implementation) is additive and doesn't require a new ADR;
allowing `side` to open a short position would — that's invariant #5
given a concrete shape at this layer too, and needs the same explicit
[01_SYSTEM_ARCHITECT.md](../01_SYSTEM_ARCHITECT.md) sign-off any
short-side change requires per that invariant's own text.

## Contract history

- **v1** ([ADR-012](../Architecture/ADR/ADR-012-OrderIntent-Contract.md)):
  initial freeze — `timestamp`, `symbol`, `side`, `quantity`,
  `order_type`, `limit_price`, `time_in_force`, `reference_price`,
  `stop_loss`, `take_profit`, `idempotency_key`, `reasoning`,
  `execution_reference`, `metadata`. No implementation exists yet; this
  is the contract Milestone 7 is built against, not a retrofit onto
  existing code.

## Enforcement

Not yet mechanically enforced — there is no `execution.models` module
yet. The first implementation ships `tests/execution/test_models.py`
enforcing every constraint in the Required Fields table and the
Invariants list above, in the same change that adds the module, matching
every other contract in this handbook.
`tests/contracts/test_orderintent_contract.py` (added to the existing
`tests/contracts/` suite) verifies the frozen field set, version
metadata, and serialization round-trip the same way the
`FeatureVector`/`RegimeState`/`StrategyDecision`/`ExecutionDecision`
contract tests already do.

## Ownership

Build and maintain: [Backend Engineer](../03_BACKEND_ENGINEER.md) — owns
broker connectivity and order lifecycle per that role's existing mandate
over `broker/order_executor.py`, extended to `src/execution/`. The
volatility-based stop-loss sizing this contract requires but doesn't
itself compute is a [Quant Researcher](../04_QUANT_RESEARCHER.md)
concern (it depends on `src/features`'s ATR/volatility features), so
building it is a joint effort, not sole Backend Engineer ownership.
Binding on every consumer: the eventual `BrokerAdapter` (this milestone),
and any future non-Alpaca broker integration. A consumer that needs a
capability this contract doesn't provide raises it against this
document — it doesn't reach into `src/execution/` internals or a specific
broker adapter to work around it.
