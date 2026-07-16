# ADR-027: Runtime Market Data Loop Design (Phase A)

**Status**: Accepted
**Date**: 2026-07-15
**Milestone**: Post-`v2.0.0` continuous evolution — Trading Validation / Runtime, Phase A

## Context

`v2.0.0` marked the planned architecture complete: every `src/`
package from `market_data` through `ops` was built, tested, and
benchmarked in isolation, but nothing ever strung them into a
continuously-running process. The legacy `regime-trader/main.py`
skeleton describes the intended shape (three concurrent pipelines
under one asyncio loop) but raises `NotImplementedError` by design —
several of its dependencies (`broker/alpaca_client.py`'s live wiring,
`core/signal_generator.py`, a trained-HMM model store) were never
built there.

Per direct instruction, this work is explicitly *not* organized as
"Milestone 13" — the roadmap is done; this is continuous evolution,
one small reviewed increment at a time rather than one large build.
The instruction specified seven phases (A through G: market data →
features → regime → strategy → orchestration → risk → paper
execution), each its own reviewed increment, built in a dedicated
`src/app/` runtime package rather than extending the legacy
`regime-trader/main.py`. This ADR covers Phase A only: connect, fetch
bars on an interval, normalize, log. No features, no HMM, no trading.

Phase A's build also directly exercised `AlpacaHistoricalProvider`
against a live Alpaca paper account for the first time in this
project's history (see that module's updated docstring) and surfaced
a real gap in the process: querying without an explicit `feed`
defaults to Alpaca's SIP feed, which a free-tier account cannot query
for data less than ~15 minutes old (`403 subscription does not permit
querying recent SIP data`).

## Decision

### 1. `AlpacaHistoricalProvider` gains a `feed` parameter, defaulting to `DataFeed.IEX`

`AlpacaStreamingProvider._default_stream_client` already hardcoded
`feed=DataFeed.IEX` — the two providers were silently inconsistent,
and the inconsistency was invisible until this milestone's live
verification actually hit it. `AlpacaHistoricalProvider.__init__` now
accepts `feed: DataFeed = DataFeed.IEX`, threaded into every
`StockBarsRequest`. Passing `feed=DataFeed.SIP` explicitly remains
available for a paid subscription; the default just stops silently
assuming one exists. No `HistoricalDataProvider` Protocol signature
changed — this is a pure implementation-level fix, not a contract
change.

### 2. `src/app/` -- a new, separate runtime package

Not an extension of `regime-trader/main.py`: that skeleton's
unresolved `NotImplementedError`s are a different, larger problem than
Phase A needs to solve, and reusing it would mean either fixing all of
them at once or building around still-broken code. `src/app/` starts
clean, wiring only what Phase A actually needs, with the same
extras-scope discipline every other package here follows (`.[dev,
market-data]` covers everything it imports — see `pyproject.toml`'s
comment block).

### 3. `MarketDataLoop` implements `common.interfaces.Service`

The same `start()`/`stop()` async lifecycle shape
`AlpacaStreamingProvider` already uses, including the identical
idempotent-`stop()`-flag pattern (`self._stop_requested`). A future
supervisor holding either one doesn't need to know which it has. A
fetch failure for one symbol is caught, logged
(`market_data_fetch_failed`), and never stops the loop or crashes the
process — the same "one bad tick doesn't kill the process" convention
`AlpacaStreamingProvider.start()`'s reconnect-with-backoff loop already
established for streaming. `stop()` takes effect on the next poll
cycle (up to `poll_interval_seconds` later) — accepted for Phase A
since no trading happens here; a tighter shutdown bound would matter
once orders are involved, not before.

### 4. `app.bootstrap.build_market_data_loop`: composition only, provider injectable

Validates required secrets (`ALPACA_API_KEY`/`ALPACA_SECRET_KEY`) via
`ops.validation` *before* constructing the default
`AlpacaHistoricalProvider` — the provider's own constructor would
otherwise discover a missing key itself and raise
`market_data.errors.ProviderAuthenticationError`, a less informative
failure than `ops.validation`'s "every missing secret in one pass"
report. Re-validated (cheap) inside the subsequent
`ops.startup.build_runtime_context` call so there's exactly one place
that produces the final `RuntimeContext`. `provider` is an injectable
parameter (defaults to the real `AlpacaHistoricalProvider`), matching
the DI convention every constructor in this codebase follows —
without it, no test could exercise `build_market_data_loop` without
either hitting the network or monkeypatching SDK internals.

Only `ops.checks.market_data_check` is used for the startup health
gate — the other nine checks in `ops.checks` (feature registry, HMM
model, risk service, ...) describe subsystems no code path in this
runtime reaches yet. Including them would just be permanently-failing
noise, not a real signal; later phases extend this list as they wire
in the pipeline stages those checks actually describe.

### 5. `app.main`: signal-driven graceful shutdown, thin and largely untested

`python -m app` registers `SIGINT`/`SIGTERM` handlers that set an
`asyncio.Event`, then awaits it before calling `loop.stop()`. This
function's body is not unit-tested — meaningfully exercising OS signal
delivery requires a real subprocess, not a unit test, the same honest,
documented gap this codebase already accepts for
`nlp.sentiment.FinBertSentimentScorer`'s untested body. What's
testable without a subprocess (the module-level default configuration)
is tested; the signal-handling wiring itself is reviewed by inspection
instead.

## Consequences

- `src/ops`'s ten health-check factories now have their first real
  consumer, closing part of the "wiring not yet authorized" gap every
  M12 ADR flagged as future work.
- The `AlpacaHistoricalProvider` feed fix benefits every future
  consumer of that provider, not just `app` — anyone constructing one
  without a paid SIP subscription now gets working behavior by
  default instead of a confusing 403.
- Adding Phase B (features) means extending `app.bootstrap`'s checks
  list and `app.runtime`'s per-symbol processing, not rewriting either
  — the `Service` lifecycle and injectable-provider pattern established
  here carry forward unchanged.
- Trade-off, accepted: Phase A's symbol list and poll interval are a
  hardcoded module-level default in `app.main`
  (`MarketDataLoopConfig(symbols=("AAPL",), ...)`) — a real
  configuration source (env vars, `config/*.yaml`) is deferred to a
  later phase rather than built speculatively now, the same "build the
  mechanism before the exact configuration surface" discipline this
  handbook has followed since Milestone 1.
- Trade-off, accepted: the real-provider-construction path in
  `build_market_data_loop` (when `provider=None`) is not exercised by
  any test, since doing so would require either a real network call or
  mocking `alpaca-py`'s SDK internals — the same "don't hit a live
  external service from a unit test" boundary
  `tests/market_data/test_alpaca_historical.py` already draws for
  `AlpacaHistoricalProvider` itself.

## Alternatives Considered

- **Extend `regime-trader/main.py` instead of building `src/app/`** —
  rejected per direct instruction and for a concrete reason: that
  skeleton's `NotImplementedError`s describe a materially larger,
  unrelated set of problems (a full signal generator, a model store)
  that Phase A doesn't need solved to fetch and log bars.
- **Poll continuously with no interval, or stream via
  `AlpacaStreamingProvider` instead of polling
  `AlpacaHistoricalProvider`** — rejected for Phase A: the eventual
  bar-based regime strategy this platform was designed around (see
  `regime-trader/main.py`'s own "5-Minute Structural Loop" framing)
  needs periodic completed-bar fetches, not a continuous tick/quote
  stream; polling is simpler to reason about and test. Streaming
  remains available via the already-built `AlpacaStreamingProvider`
  for a future phase that genuinely needs tick-level data.
- **Include all ten `ops.checks` factories in the startup health gate**
  — rejected: nine of them describe subsystems (HMM, strategy, risk,
  execution, memory, NLP) this runtime doesn't touch yet; including
  them would make every Phase A startup fail a check that can never
  pass until later phases exist.
- **Give `MarketDataLoop` a tighter, event-driven shutdown instead of
  "takes effect on the next poll cycle"** — rejected for Phase A: no
  trading happens in this loop, so a shutdown bounded by
  `poll_interval_seconds` is acceptable; revisit once a later phase
  makes shutdown latency safety-relevant.
