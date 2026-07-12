# ADR-002: Market Data Platform

**Status**: Accepted
**Date**: 2026-07-12
**Milestone**: [2 — Market Data](../../../../PROJECT_STATUS.md)

## Context

Milestone 2 built the market data platform: provider interfaces, domain
models, Alpaca historical + streaming providers, Parquet/DuckDB storage,
validation, and a replay harness — with the explicit outcome that every
future subsystem (HMM, backtesting, NLP, execution) should eventually
consume the same interfaces rather than each growing its own data-fetching
logic. That outcome forced several structural decisions before a single
provider could be written, and this milestone also had to resolve a real
tension left open by [ADR-001](ADR-001-Foundation.md) Decision 6: Known
Gaps item 2 (`broker/alpaca_client.py`) explicitly lives inside
`regime-trader/`, the exact directory Milestone 1 committed to not
touching. This record captures how that tension was resolved and the
platform's other significant decisions.

---

## Decision 1: A new `src/market_data` package, not `regime-trader/broker/`

**Status**: Accepted

### Context

Known Gaps item 2 names `broker/alpaca_client.py` — inside
`regime-trader/`, the directory this repository's own tooling (Ruff,
Black, MyPy, CI) still excludes per Milestone 1's scoping. Building the
full market data platform directly there would mean either leaving all of
it untyped/unlinted, or unilaterally expanding tooling scope to the whole
of `regime-trader/` as a side effect of a feature milestone — not a
decision Milestone 2 owns.

### Decision

Build the platform as a new, independent, fully-tooled package at
`src/market_data/`, structured and packaged the same way `src/common/`
was in Milestone 1 (own `pyproject.toml` extras group, full Ruff/Black/
MyPy/Pytest coverage, `py.typed` marker). `regime-trader/` gets exactly
one new file, a thin adapter — see Decision 5.

### Consequences

- The entire platform (172 statements across models, interfaces, two
  providers, storage, validation, and replay) is strict-MyPy-checked,
  Ruff-linted, and has 97% test coverage from day one — the standard
  Milestone 1 set, not a lesser one.
- `market_data` has zero dependency on `regime-trader/` — it doesn't
  import anything from it, doesn't know `regime-trader/`'s module layout,
  and would work identically if `regime-trader/` didn't exist. This is
  what makes "every future subsystem consumes the same interfaces" a
  credible claim rather than an aspiration: nothing about this package
  privileges `regime-trader/` as a consumer over some future backtester or
  research notebook.
- Trade-off: two packages now exist where a single "the trading platform"
  package might eventually make more sense. Accepted deliberately — see
  [ADR-001](ADR-001-Foundation.md) Decision 6's reasoning about deferring
  `regime-trader/`'s own packaging to whichever milestone is already
  modifying that code for substantive reasons, which still applies.

### Alternatives Considered

- **Build directly in `regime-trader/broker/alpaca_client.py`** — rejected
  per the Context above: it would have forced a tooling-scope decision
  that belongs to whoever eventually migrates `regime-trader/` wholesale,
  not to this milestone.

---

## Decision 2: Provider-agnostic domain models and `Protocol` interfaces

**Status**: Accepted

### Context

`Bar`, `Trade`, `Quote`, `OrderBook`, `Snapshot`, and `CorporateAction` are
the types every future consumer will actually hold and pass around. If
they leaked vendor shape (e.g. an Alpaca SDK `Bar` with Alpaca-specific
field names/types), every consumer would be implicitly coupled to Alpaca
regardless of what `market_data.interfaces` declared.

### Decision

`market_data/models.py` imports nothing from `alpaca-py` and has no
Alpaca-shaped fields. `market_data/interfaces.py` defines
`HistoricalDataProvider`, `StreamingDataProvider`, `CorporateActionsProvider`,
and `MarketDataStorage` as `typing.Protocol`s — continuing
[ADR-001](ADR-001-Foundation.md) Decision 1's reasoning for `common`'s
interfaces, now applied to a domain with more than a hypothetical second
implementation: a second market data vendor is a realistic future need,
not a speculative one.

### Consequences

- Every provider's job is reduced to one conversion function (`_to_bar`,
  `_to_trade`, ...) at its own boundary — see `providers/alpaca_historical.
  py`'s `_to_bar` and `providers/alpaca_streaming.py`'s equivalents. A
  second vendor implements the same `Protocol`s and needs zero changes
  anywhere else.
- `StreamingDataProvider` composes `common.interfaces.Service` (frozen in
  Milestone 1) rather than redefining its own start/stop shape — direct
  proof that Milestone 1's foundation is genuinely reusable, not just
  internally consistent.
- Every model validates its own invariants at construction (`Bar` rejects
  a naive or non-UTC timestamp, an OHLC violation; `CorporateAction`
  requires a `ratio` for a split) — a malformed record fails at the
  provider boundary where the bad data was parsed, not somewhere
  downstream disconnected from the cause.

### Alternatives Considered

- **Pass `pandas.DataFrame`s everywhere instead of typed model objects** —
  rejected. `regime-trader/main.py.MarketDataProvider` already returns a
  DataFrame and that contract is preserved (see Decision 5's adapter), but
  a DataFrame has no per-row invariant checking and no static typing for
  what columns exist — exactly the failure mode `Bar.__post_init__`
  exists to catch immediately instead of via a KeyError three modules
  away.

---

## Decision 3: Parquet + DuckDB, one cache, not a separate cache layer

**Status**: Accepted

### Context

Milestone 2's deliverables named four things: Parquet, DuckDB, a local
cache, and incremental updates. Read literally as four components, this
risks a redundant design — a cache sitting in front of a Parquet store
that's already on local disk is caching a cache.

### Decision

`ParquetBarStore` is simultaneously the write path, the single-symbol
read path, the local cache, and the incremental-update mechanism: every
`write_bars` call merges into whatever's already on disk for that
`(symbol, timeframe)`, deduplicating on timestamp. `DuckDBBarQuery` is a
separate, read-only, SQL-oriented layer over the same files, for the one
thing `ParquetBarStore` doesn't do well — querying across many symbols at
once — using DuckDB's ability to query Parquet files directly with no ETL
step.

### Consequences

- One durable representation of the data, not two representations that
  could drift out of sync with each other.
- `MarketDataStorage.latest_timestamp` is what makes "incremental" real:
  a caller fetches only `(latest_timestamp, now]` from a provider instead
  of re-fetching history it already has — demonstrated end-to-end in
  `tests/market_data/test_storage_parquet.py::TestIncrementalUpdates::
  test_incremental_update_pattern`.
- Trade-off: `ParquetBarStore` is not safe for concurrent writers to the
  same file, matching every other durable state file in this repository
  (see docs/engineering-handbook/05_MEMORY_ENGINEER.md) — a known,
  consistent constraint, not a gap specific to this module.

### Alternatives Considered

- **SQLite** — rejected: would have meant a second query interface
  (SQL via `sqlite3`) alongside pandas-native access, for no benefit over
  Parquet+DuckDB, which gets both columnar-storage efficiency and SQL
  access from the same files.
- **A cache layer independent of the Parquet store** (e.g. an LRU or
  TTL-based in-memory/disk cache in front of the store) — rejected as
  premature: no access pattern yet demands it, and
  [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md) Definition of Done
  #6 rules out speculative abstraction for hypothetical future needs.

---

## Decision 4: A separate `market-data` extras group

**Status**: Accepted

### Context

`regime-trader/`'s existing `trading` extras group (from
[ADR-001](ADR-001-Foundation.md) Decision 5) already includes pandas,
numpy, and alpaca-py — packages `market_data` also needs — bundled
alongside scipy, hmmlearn, torch, and transformers, none of which
`market_data` imports.

### Decision

Declare a new `market-data` extras group (`pandas`, `numpy`, `pyarrow`,
`duckdb`, `alpaca-py`) independent of `trading`, even though the two
overlap on three packages.

### Consequences

- `pip install -e ".[dev,market-data]"` — what this milestone's own CI
  job runs — never pulls in torch or transformers. Verified directly: the
  full market-data install in this environment completed without ever
  downloading either.
- Minor duplication: three package names now appear in both extras
  groups' declarations. Accepted — matching `trading`'s definition via
  self-reference would couple the two groups' version constraints
  together for no real benefit, and the duplication is small and static,
  not the kind that rots silently.

### Alternatives Considered

- **Extend `trading` to cover `market_data`'s needs and use that** —
  rejected: reintroduces exactly the "install torch to touch market data
  code" problem [ADR-001](ADR-001-Foundation.md) Decision 5 already
  rejected once for `common`.

---

## Decision 5: One thin adapter file bridges the two packages

**Status**: Accepted

### Context

`regime-trader/main.py` already defines the exact contract a market data
source must satisfy (`MarketDataProvider.get_ohlcv_history(ticker,
lookback_days) -> pd.DataFrame`) and already has the injection point
wired (`market_data=_NotYetImplemented(...)`) — see Decision 1. Something
has to translate between that contract and `market_data`'s own
`HistoricalDataProvider.get_bars(symbol, start, end, timeframe) ->
list[Bar]`.

### Decision

`regime-trader/broker/alpaca_client.py` — the file Known Gaps item 2
already named — is a single class, `AlpacaMarketDataClient`, whose only
job is: convert `lookback_days` into an explicit `[start, end)` window
using an injected `common.interfaces.Clock`, call
`AlpacaHistoricalProvider.get_bars` with `Timeframe.DAY_1`, and reshape
the result into the exact ascending-time-indexed, five-column DataFrame
`main.py.MarketDataProvider` promises. It contains no retry, rate-limit,
or credential logic of its own — all of that already lives in
`AlpacaHistoricalProvider`. `main.py` is updated in the same change to
construct `AlpacaMarketDataClient()` instead of the `_NotYetImplemented`
placeholder — a two-line diff.

### Consequences

- Known Gaps item 2 is closed. `regime-trader/main.py`'s structural loop
  is no longer blocked on a `NotImplementedError` for market data,
  narrowing the remaining blockers to the model store (item 3) and
  `signal_generator.py` (item 4).
- This is the one place `market_data` and `regime-trader/` touch. Neither
  package needs to know the other's internals beyond this one file's
  contract, verified by a dedicated contract test suite
  (`tests/regime_trader/test_alpaca_client_adapter.py`) asserting exactly
  the three properties docs/engineering-handbook/03_BACKEND_ENGINEER.md's
  acceptance criteria require: ascending time index, exactly the five
  OHLCV columns, no NaN gaps — plus that both real call sites
  (`FEATURE_HISTORY_LOOKBACK_DAYS=400` and
  `CORRELATION_HISTORY_LOOKBACK_DAYS=90`) produce identically shaped data.
- This is a narrow, deliberate exception to Milestone 1's "don't touch
  `regime-trader/`" posture, not an abandonment of it: one new file plus a
  two-line edit to wire it in, both covered by this repository's full
  tooling (see the updated tooling-scope note in
  [Architecture/Known Gaps.md](../Known%20Gaps.md)), not a broader
  reformat or refactor of anything already there.

### Alternatives Considered

- **Have `RegimeTraderApp` depend on `market_data.interfaces.
  HistoricalDataProvider` directly, dropping `MarketDataProvider`** —
  rejected: changing `main.py`'s `Protocol` contracts is explicitly
  [01_SYSTEM_ARCHITECT.md](../../01_SYSTEM_ARCHITECT.md)'s call to make,
  not Backend Engineer/Milestone-2 territory, and the existing contract
  (a DataFrame matching `feature_engineering.build_feature_matrix`'s
  input) has no reason to change just because a new provider package
  exists behind it.

---

## Decision 6: A custom reconnect loop, not just the SDK's own behavior

**Status**: Accepted

### Context

`regime-trader/broker/news_streamer.py`'s existing `NewsStreamer` wraps
`NewsDataStream.run()` with no reconnect logic of its own — a dropped news
connection simply stops. Milestone 2's deliverables explicitly call for
"Disconnect recovery" and "Reconnect" as tested capabilities, and a
market data feed silently going quiet is a worse failure mode than a
dropped news feed (see `AlpacaStreamingProvider`'s module docstring).

### Decision

`AlpacaStreamingProvider.start()` wraps `StockDataStream.run()` in a loop
with exponential backoff (capped, injectable delay/multiplier/max), and
separately exposes `is_stale()` (heartbeat, based on time since the last
message) and `last_latency_seconds` (gap between an event's own timestamp
and local receipt) as first-class, independently queryable properties —
not just internal retry bookkeeping.

### Consequences

- Reconnect behavior is deterministically testable: `tests/market_data/
  test_alpaca_streaming.py::TestReconnect` drives a fake client through
  scripted disconnects and asserts on `reconnect_count` and the exact
  backoff delays via an injected async `sleep`, without a real dropped
  connection or real elapsed time anywhere in the test suite.
- A future monitoring/alerting integration (Milestone 10 — see
  [Architecture/Production Deployment.md](../Production%20Deployment.md))
  has `is_stale()` and `last_latency_seconds` ready to poll; this
  milestone doesn't wire them to anything yet, deliberately — that's
  production-deployment scope, not market-data-platform scope.

### Alternatives Considered

- **Rely on whatever reconnect behavior `StockDataStream` has internally**
  — rejected: unverified and not something this repository controls or
  can test deterministically. Building the reconnect loop as first-party
  code, on top of the SDK's blocking `.run()`, keeps the guarantee
  ("this system retries a dropped market data connection with backoff")
  something this test suite actually proves rather than assumes.

---

## Verification note

Every Alpaca SDK usage in this milestone (`StockHistoricalDataClient.
get_stock_bars`, `CorporateActionsClient.get_corporate_actions`,
`StockDataStream.subscribe_bars/trades/quotes`, and the exact response
model shapes — `BarSet.data`, `CorporateActionsSet.data`, per-action-type
models) was confirmed by directly importing and inspecting the actually-
installed `alpaca-py==0.43.5` in this environment before being coded
against, catching one real bug in the process: Alpaca's corporate-actions
`ex_date` is a plain `datetime.date`, not a `datetime`, which the initial
implementation would have crashed on the first time a real split or
dividend was fetched (see `_ex_date_to_utc_datetime` and its dedicated
test coverage). None of this has been exercised against a live Alpaca
account — no credentials are available in this environment — so
end-to-end behavior against the real API (as opposed to the real SDK's
type/response shapes) remains unverified until paper-trading credentials
are available.
