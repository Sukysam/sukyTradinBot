# 03 — Backend Engineer

## Mandate

Build and maintain the plumbing: broker connectivity, order lifecycle, and
the async wiring in `main.py` that holds the event-driven execution model
together. Not responsible for *what* trade to make (Signal Orchestrator) or
*whether* it's allowed (Risk Manager) — only for reliably executing the
decision once both have signed off.

## Capability ownership

| Capability | This role's responsibility |
|---|---|
| Alpaca Broker Integration | Full ownership of the implementation (order execution done; historical data client planned) |
| Event-Driven Execution | Implements the transport side (news WebSocket) and the lifecycle wiring; shape owned by System Architect |

## Owns

- `broker/order_executor.py` — OCO/OTO bracket order construction and
  submission via `alpaca-py`.
- `broker/news_streamer.py` — the Alpaca News WebSocket transport, the
  event source for the event-driven execution pipeline.
- `broker/alpaca_client.py` — **not yet built**; historical OHLCV fetching.
  Top backend priority per [Technical Planner](02_TECHNICAL_PLANNER.md).
- `main.py`'s lifecycle code (`run`, `_shutdown`, signal handling, task
  wiring) — not its `Protocol` contracts, which belong to
  [System Architect](01_SYSTEM_ARCHITECT.md).

## Core responsibilities & workflows

1. **Order construction correctness.** Every entry order carries a
   mandatory stop-loss leg and, when supplied, a take-profit leg, sized to
   whole shares via `size_to_shares`, validated against Alpaca's two
   client-side-unenforced constraints (whole-share bracket quantity,
   mandatory stop) before submission.
2. **Transport reliability.** `NewsStreamer` reconnects and surfaces
   failures loudly (`logger.exception`) rather than silently dropping
   headlines — a missed headline is a missed catalyst-trade opportunity,
   not a benign gap.
3. **Historical data contract delivery.** When building `alpaca_client.py`,
   match `MarketDataProvider`'s contract exactly, including pagination for
   `FEATURE_HISTORY_LOOKBACK_DAYS` (400 days) and
   `CORRELATION_HISTORY_LOOKBACK_DAYS` (90 days) windows.
4. **Position lifecycle.** `liquidate_position` (single-ticker) and
   `liquidate_all_positions` (circuit-breaker triggered) stay distinct
   methods with distinct log severities — never merged.

## Acceptance criteria

- Every new order-submission code path is covered by a unit test that
  mocks `TradingClient` and asserts: correct `OrderClass` (OTO vs.
  BRACKET) selection, correct whole-share truncation, and rejection when
  `stop_price >= entry_price` or `take_profit_price <= entry_price`.
- `alpaca_client.py`, once built, ships with a contract test asserting its
  return value satisfies `MarketDataProvider`: ascending time index,
  exactly the columns `['open','high','low','close','volume']`, no
  silent NaN gaps within the requested lookback window.
- No PR merges that calls a blocking `alpaca-py` or `NewsDataStream` method
  directly inside an `async def` without `asyncio.to_thread`.
- Every new broker-layer exception path logs at a severity matching its
  operational impact (`CRITICAL` for anything that could leave a position
  unmanaged, `WARNING` for a single failed non-critical call, `ERROR` for
  a failed submission that the caller will retry or report).

## Coding standards

Follow [Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md)
and [Standards/Coding Standards.md](Standards/Coding%20Standards.md).
Backend-specific additions:

- Never construct `TradingClient` or any Alpaca SDK client inside a
  business-logic module (`order_executor.py` receives it injected) — client
  construction and credential handling live in `main.py`/`alpaca_client.py`
  only, so every other module stays trivially testable with a fake.
- Every Alpaca SDK call site that can raise `APIError` catches it
  explicitly and returns a typed result (`OrderResult`), never lets it
  propagate to the caller as a raw SDK exception — callers in `core/`
  should never need to know `alpaca-py` exists.
- Retry/backoff logic for transient API errors belongs at the client layer
  (`alpaca_client.py`), not scattered into call sites — one policy, one
  place.

## Communication protocols

- Any change to `OrderExecutor.submit_entry_order`'s signature is flagged
  to [System Architect](01_SYSTEM_ARCHITECT.md) before merge — it's called
  from `main.py._evaluate_and_submit` with fields derived from
  `TradeDecision`, so a signature change ripples into a `Protocol` contract
  this role doesn't own.
- Broker-layer incidents (failed liquidation, dropped news connection) are
  reported using the severity language in
  [Standards/Communication Protocols.md](Standards/Communication%20Protocols.md) —
  `liquidate_all_positions` failures are always reported as incidents, not
  routine log noise, per [SOPs/Incident Response Runbook.md](SOPs/Incident%20Response%20Runbook.md).
- When `alpaca_client.py` ships, announce the Known Gap closure in the same
  PR (see [Documentation Engineer](11_DOCUMENTATION_ENGINEER.md)'s
  process) so downstream roles (Quant Researcher, for backtesting; System
  Architect, for the placeholder wiring) know it's safe to depend on.

## Must escalate

- Adding a short-side order path — `order_executor.py` is explicitly
  long-only by design; this is a product decision, not an implementation
  detail.
- Removing or weakening either client-side validation in
  `submit_entry_order` (whole-share truncation, mandatory stop) — both
  exist because `alpaca-py`'s request models don't enforce them and the
  API fails differently otherwise, confirmed by direct SDK inspection.
- Any change to `OrderExecutor`'s public method signatures.

## Pitfalls specific to this seam

- `size_to_shares` **truncates down**. A trade sized for $1,000 notional
  leaving a $999 remainder is normal, not a bug — Alpaca rejects
  fractional `qty` on bracket/OTO orders.
- `NewsDataStream.run()` owns its own internal event loop
  (`asyncio.run(self._run_forever())`, confirmed by SDK inspection) — it
  cannot be awaited directly inside `main.py`'s loop. `NewsStreamer.start()`
  wraps it in `asyncio.to_thread` for exactly this reason; don't "simplify"
  this away.
- When building `alpaca_client.py`, remember `main.py` calls
  `get_ohlcv_history` with two different lookback windows for two different
  purposes (`FEATURE_HISTORY_LOOKBACK_DAYS=400` for feature warmup,
  `CORRELATION_HISTORY_LOOKBACK_DAYS=90` for the risk manager's correlation
  cache) — both must return data shaped identically regardless of window
  size.
