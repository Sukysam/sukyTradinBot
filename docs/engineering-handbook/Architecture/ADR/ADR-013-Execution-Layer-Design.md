# ADR-013: Execution Layer Design

**Status**: Accepted
**Date**: 2026-07-13
**Milestone**: [7 — Execution Layer](../../../../PROJECT_STATUS.md)

## Context

Milestone 7 built `src/execution/`: the first real consumer of the
frozen `ExecutionDecision` contract, converting it (with current
`PortfolioState`) into an `OrderIntent`. Its charter is narrow and
explicit — is an order needed, at what size and price, with what stop —
never a broker call. This record covers the implementation decisions
behind it, all made *after* `OrderIntent` itself was already frozen
([ADR-012](ADR-012-OrderIntent-Contract.md)) — every decision here is
explicitly implementation, not contract.

ADR-012's own Context flagged a real, unresolved gap: neither
`StrategyDecision` nor `ExecutionDecision` carries price information.
Resolving that gap — without widening either frozen contract — is this
milestone's central design problem, and the origin of every decision
below.

Unlike Milestone 6, this is not a packaging job for an existing module.
`regime-trader/broker/order_executor.py::OrderExecutor.submit_entry_order`
provides a real, tested reference for order *construction and
submission*, but the *price/stop discovery* problem this milestone
solves has no legacy precedent at all — the old system's `TradeDecision`
already arrived with `entry_price`/`stop_price` pre-computed by
`signal_generator.py`, a component that was never built (see
[Known Gaps.md](../Known%20Gaps.md) item 4).

---

## Decision 1: `ExecutionContext`/`FeatureSnapshot` are internal, deliberately unfrozen value objects

**Status**: Accepted

### Context

`OrderIntent` needs a `reference_price` and (for a `BUY`) a `stop_loss`,
but ADR-012 explicitly ruled out adding price fields to `StrategyDecision`
or `ExecutionDecision`. Something has to carry a live price and a
volatility reading from wherever they're sourced to the point
`OrderIntent` is constructed.

### Decision

Two new value objects, `execution.models.ExecutionContext` (a market
observation: `reference_price`, `bid`/`ask`/`spread`, `tick_size`,
`price_source`) and `execution.models.FeatureSnapshot` (`atr_14`,
`realized_volatility_20`), carry this data — both plain `@dataclass
(frozen=True)` value objects with light validation, **not** frozen
contracts per [Standards/](../../Standards/): no Standards doc, no
version history, no cross-package `tests/contracts/` coverage. They never
leave `src/execution` and are never embedded in an `OrderIntent`
(`OrderIntent.reference_price` is a plain `float`, not a nested
`ExecutionContext`).

This follows directly from the principle ADR-012 was amended with before
this milestone began: *execution contracts describe trading intent, not
market observations.* `OrderIntent` is durable; a live quote or an ATR
reading at build time is transient and true only at that instant. Freezing
`ExecutionContext`'s shape would mean every future consumer forever
agrees on exactly which market observations exist, for no benefit
`reference_price` alone doesn't already provide.

### Consequences

- `ExecutionContext`/`FeatureSnapshot` can grow or change shape freely as
  real market-data needs evolve (a real bid/ask feed, additional
  volatility measures) without triggering a contract version bump or a
  new ADR — ordinary code review is sufficient.
- `FeatureSnapshot` carries only `atr_14`/`realized_volatility_20` — a
  restriction, not an oversight. `src/features`'s manifest documents
  `atr_50` nowhere; the field list is grounded in features that actually
  exist (`config/feature_manifest.yaml`), not the illustrative example
  set from planning discussion.
- Trade-off, accepted: because these types aren't frozen, there's no
  contract-level backward-compatibility guarantee if a future change
  reshapes them — acceptable since nothing outside `src/execution`
  depends on them by design.

### Alternatives Considered

- **Thread the full `FeatureVector` through the execution layer** —
  rejected: couples order construction to every feature this platform
  ever adds, most of which have nothing to do with sizing a stop, and
  `FeatureVector` isn't even available at this point in the pipeline
  today (`RegimeState`/`StrategyDecision`/`ExecutionDecision` don't carry
  one forward).
- **Add `reference_price`/`stop_loss` fields directly to
  `ExecutionDecision`** — rejected in ADR-012 already; not reconsidered
  here.

---

## Decision 2: Three pluggable interfaces — `MarketSnapshotProvider`, `FeatureSnapshotProvider`, `StopLossPolicy` — plus a fourth, `BrokerAdapter`, kept structurally separate

**Status**: Accepted

### Context

Building an `OrderIntent` requires three independent capabilities: fetch
a current price, fetch current volatility, and turn a price/volatility
pair into a stop level. Each has more than one plausible implementation
(a bar-close price today, a live quote later; an ATR-based stop, a
fixed-percent fallback), and none of the three should need to know the
others exist.

### Decision

`execution.interfaces` defines four `Protocol`s: `MarketSnapshotProvider.
get_snapshot(symbol) -> ExecutionContext`, `FeatureSnapshotProvider.
get_latest(symbol) -> FeatureSnapshot`, `StopLossPolicy.compute_stop_loss
(context, feature_snapshot) -> float`, and `BrokerAdapter.submit_order
(intent) -> BrokerSubmissionResult` / `.cancel_order(id) -> bool`.
`OrderBuilder` and `ExecutionService` depend only on the first three;
`BrokerAdapter` is used by a separate submission step (`execution.retry.
submit_with_retry`), never by `ExecutionService` itself — building an
`OrderIntent` and submitting one are two different operations with two
different failure modes (a snapshot fetch failing is not the same
problem as a broker rejecting an order), and conflating them into one
service would make both harder to test in isolation.

### Consequences

- Swapping `ATRStopPolicy` for `FixedPercentPolicy` (or a future
  asset-class-specific policy) never touches `OrderBuilder`.
- `ExecutionService` can be fully exercised in tests with fake providers
  and no real market data, broker, or network dependency — see
  `tests/execution/test_execution_service.py`.
- `BrokerAdapter`'s concrete implementation (`AlpacaBrokerAdapter`) is
  the *only* module under `src/execution` that imports `alpaca-py` —
  checkable by grep, not just documented convention.

### Alternatives Considered

- **One `ExecutionService` method that also submits the order** —
  rejected: conflates "decide what order to build" with "submit it to a
  broker," two operations with different retry/idempotency semantics
  (see Decision 4) and different testing needs.

---

## Decision 3: `router.py` reconciles target allocation against current position — a genuinely new capability with a documented approximation

**Status**: Accepted

### Context

Neither `StrategyDecision` nor `ExecutionDecision` expresses "buy N
shares" — both are stateless target-allocation snapshots, re-evaluated
fresh every cycle with no memory of what was submitted last cycle.
Something has to diff today's target against today's actual position to
decide whether an order is needed at all, and if so, its side and
quantity. No legacy module does this either — the old `TradeDecision`
already arrived with an order-shaped `notional_value`, never a
rebalancing delta.

### Decision

`execution.router.route(execution_decision, portfolio, reference_price)`
computes `target_value = approved_allocation * portfolio.equity`,
diffs it against the existing position's `market_value` for that symbol,
and returns a `BUY`/`SELL` `RoutingDecision` with a whole-share quantity,
or `None` if the delta is below `MIN_ORDER_NOTIONAL` ($1) or truncates to
zero shares. A `SELL` quantity is capped at `current_position_value /
reference_price` — `Position.market_value` is a dollar mark-to-market
figure, not a stored share count (same as in `core/risk_manager.py`), so
this is an **approximation**, not an exact share count, the same
documented caveat `ProposedTrade.dollar_risk` already carries in the
legacy module. It never oversells (a hard requirement given invariant
#5 — a `SELL` only ever exits an existing long, never opens a short), but
the exact quantity may differ slightly from a broker's own books if
`reference_price` has moved since the position was last marked.

### Consequences

- `OrderIntent` is now reachable end-to-end: `ExecutionDecision`'s
  fraction becomes a real, boundable share count.
- The approximation is explicit and tested
  (`tests/execution/test_router.py::TestSellRouting::
  test_sell_quantity_never_exceeds_current_position`), not a silent
  source of a future oversell bug.
- Trade-off, accepted: `MIN_ORDER_NOTIONAL = 1.0` is a practical,
  undocumented-by-spec constant to avoid dust orders — not derived from
  any cited requirement, flagged here rather than presented as
  spec-grounded.

### Alternatives Considered

- **Store share counts on `Position` instead of only `market_value`** —
  rejected: `Position` is shared with `src/risk`, already frozen in shape
  by that package's own design (not a contract, but changing it ripples
  into every risk validator); not worth widening for this one consumer
  when the approximation is small and already bounded.

---

## Decision 4: Retry and idempotency are `execution.retry`'s job, bridging a result-based failure into `common.retry`'s exception-based mechanism

**Status**: Accepted

### Context

`common.retry.call_with_retry` retries on *exceptions*.
`BrokerAdapter.submit_order` never raises for an ordinary submission
failure — it returns `BrokerSubmissionResult(submitted=False, error=...)`,
matching `OrderExecutor`'s existing pattern of catching `APIError` and
returning a typed result. These two shapes don't compose directly.

### Decision

`execution.retry.submit_with_retry` wraps a `BrokerAdapter.submit_order`
call in a closure that raises `TransientBrokerError` when the result says
`submitted=False`, retries via `call_with_retry`, and translates a final
`RetryExhaustedError` back into a `BrokerSubmissionResult(submitted=
False, ...)` — so the public shape callers see is always a
`BrokerSubmissionResult`, retries are entirely an internal
implementation detail. Every retry resubmits the *same*
`OrderIntent.idempotency_key` as `client_order_id`; the broker's own
idempotent handling of a repeated `client_order_id` (not anything in this
module) is what actually prevents a duplicate fill across retries.

### Consequences

- One policy, one place, per
  [03_BACKEND_ENGINEER.md](../../03_BACKEND_ENGINEER.md)'s existing
  rule — no retry logic scattered into `BrokerAdapter` implementations
  or call sites.
- `OrderIntent.idempotency_key` being caller-supplied (ADR-012 Decision
  3) is what makes this safe: retries share the same value, unlike the
  legacy `order_executor.py`'s per-call `uuid.uuid4()`, which could not
  have supported this.

### Alternatives Considered

- **Have `BrokerAdapter.submit_order` raise on failure directly, so
  `call_with_retry` needs no bridging** — rejected: would make
  `BrokerAdapter.submit_order`'s contract inconsistent with
  `OrderExecutor.submit_entry_order`'s existing, deliberate "catch
  `APIError`, return a typed result" pattern that
  [03_BACKEND_ENGINEER.md](../../03_BACKEND_ENGINEER.md) already
  establishes as this codebase's convention for broker-layer calls.

---

## Deliberately deferred

- **`LIMIT` orders.** `OrderType.LIMIT`/`limit_price` exist in the frozen
  contract (ADR-012), but `AlpacaBrokerAdapter.submit_order` raises
  `NotImplementedError` for one today — no current requirement or legacy
  precedent calls for a limit order.
- **Live bid/ask.** `BarSnapshotProvider` always sets `bid`/`ask`/`spread`
  to `None` — a `Bar` carries no quote data. A `MarketSnapshotProvider`
  backed by `market_data.interfaces.StreamingDataProvider`'s live quotes
  is future work.
- **`VolatilityTierPolicy`.** No concrete tiered stop-sizing formula
  exists anywhere in this codebase to ground one in (the legacy
  `core/risk_manager.py` comment references it without a formula) —
  `ATRStopPolicy`/`FixedPercentPolicy` cover today's real need without
  inventing an ungrounded tier scheme.
- **A real tick-size table.** `DEFAULT_TICK_SIZE = 0.01` is a flat
  placeholder for all US equities, not a venue-specific lookup.
- **Whole-book actions** (liquidate-all, halt-all) — already flagged as
  out of `ExecutionDecision`'s scope in ADR-010; this milestone doesn't
  reintroduce them at the `OrderIntent` layer either.
