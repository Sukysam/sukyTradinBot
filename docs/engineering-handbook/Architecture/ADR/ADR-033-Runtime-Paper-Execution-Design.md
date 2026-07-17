# ADR-033: Runtime Paper Execution Design (Phase G)

**Status**: Accepted
**Date**: 2026-07-17
**Milestone**: Post-`v2.0.0` continuous evolution — Trading Validation / Runtime, Phase G (final phase)

## Context

Phase F (ADR-032) proved the runtime can produce a genuine
`ExecutionDecision` end to end while remaining completely paper-safe by
construction — no code path in that phase could reach a broker. Phase G
is fundamentally different in kind from every phase before it: it
crosses the boundary from decision generation into broker interaction.
Per direct instruction, this is the final phase of the 7-phase runtime
plan (`ExecutionDecision -> ExecutionEmitter -> OrderIntent ->
BrokerAdapter`), and the runtime should stop there — no fill handling,
trade lifecycle tracking, position reconciliation, or memory/experience
recording. Those are explicitly deferred, future work, downstream of a
stable, observed submission path.

Given the change in kind, the instruction was explicit about structure
and safety, not just scope:

- `ExecutionEmitter` is responsible for exactly one transformation —
  `ExecutionDecision -> ExecutionService -> OrderIntent`. Nothing else.
- Broker submission is a **second, separate stage** — `OrderIntent ->
  BrokerAdapter -> BrokerSubmissionResult` — because keeping order
  *construction* separate from order *submission* is what makes
  retries, simulation, and a future paper/live switch straightforward.
- The runtime must default to `paper_trading = True` and require an
  explicit configuration change before live order submission is ever
  enabled.

## Decision

### 1. Two stages, not one: `ExecutionEmitter` and `BrokerSubmissionEmitter`

`app/execution_loop.py` defines two classes, not one. `ExecutionEmitter.
handle_frame` calls `frame.require_execution_decision()`, fetches
`PortfolioState` from an injected provider, calls `ExecutionService.
decide`, and enriches the frame with the resulting `OrderIntent` — it
never imports or calls anything under `execution.broker_adapter` or
`execution.retry`. `BrokerSubmissionEmitter.handle_frame` calls `frame.
require_order_intent()` and submits via `execution.retry.
submit_with_retry` (the package's own already-built, sanctioned retry
mechanism — three attempts with backoff by default, resubmitting the
same `OrderIntent.idempotency_key` as `client_order_id` each time so the
broker's own idempotent handling prevents a duplicate fill across
retries), enriching the frame with the resulting
`BrokerSubmissionResult`. This is the first split in this runtime where
two emitters divide what could have been one class's responsibility —
justified because order construction and order submission have
genuinely different failure modes, different retry semantics, and
different simulation needs (a backtest or paper-trace can swap or omit
either stage independently).

An unapproved `ExecutionDecision` producing `order_intent is None` from
`ExecutionService.decide` is treated as an ordinary, expected outcome —
same convention as `RiskEmitter` treating a rejected decision as
ordinary, not a failure: no error counter, an informational log, and the
frame's journey ends there. A rejected `BrokerSubmissionResult`
(`submitted=False`, e.g. exhausted retries) is *not* treated as a
`BrokerSubmissionEmitter` failure either — the frame is still enriched
and returned, since "the broker declined the order" is a legitimate,
loggable outcome distinct from this stage itself malfunctioning.
`BrokerSubmissionEmitter`'s own try/except around `submit_with_retry` is
a last-resort safety net for a genuinely unexpected exception in the
adapter or retry plumbing — `submit_with_retry` is documented to never
raise under normal operation (a `RetryExhaustedError` is caught
internally and translated into a failed `BrokerSubmissionResult`), so
this path exists only to keep a wiring bug from crashing the loop.

### 2. Paper trading by default: reuse `AlpacaCredentials.paper`, don't invent a new flag

`market_data.auth.AlpacaCredentials.paper: bool` has defaulted to `True`
via the `ALPACA_PAPER` env var since Milestone 2, matching this
project's documented invariant that an unset value must never silently
mean live trading. `app.bootstrap._default_broker_adapter()` reuses this
existing mechanism directly — `TradingClient(api_key=..., secret_key=...,
paper=credentials.paper)` — rather than introducing a second,
independent paper/live flag that could drift out of sync with the one
already governing every other Alpaca-touching code path in this
codebase. If `credentials.paper` is ever `False`, `_default_broker_adapter`
logs a loud `logger.warning(..., extra={"event": "live_trading_enabled"})`
before returning the adapter — the runtime doesn't refuse to build (an
operator may deliberately want live trading), but it makes the
transition impossible to miss in the logs. Enabling live trading
therefore requires an explicit `ALPACA_PAPER=false` in the environment;
no code change in this runtime can turn it on.

### 3. `build_execution_loop`: the full A-G composition root

`app.bootstrap.build_execution_loop` composes all seven stages
(`FeatureVectorEmitter -> RegimeEmitter -> StrategyEmitter ->
OrchestrationEmitter -> RiskEmitter -> ExecutionEmitter ->
BrokerSubmissionEmitter`) via `app.pipeline.compose_pipeline`, following
the same flat-composition pattern every `build_*_loop` since Phase E has
used. Two new dependencies, `execution_service`/`broker_adapter`, follow
the "does this have a real, working default" question already answered
three different ways in this runtime:

- `execution_service` defaults to `ExecutionService.default
  (resolved_provider, execution_config)` — needs only an already-
  resolved `HistoricalDataProvider`, no trained model or per-model
  mapping, so it defaults cleanly (same category as `risk_service` in
  ADR-032).
- `broker_adapter` defaults to a real `AlpacaBrokerAdapter` via
  `_default_broker_adapter()` (Decision 2) — needs only the same
  `ALPACA_*` credentials every other default in this bootstrap module
  already requires.

`build_execution_loop` resolves its own `HistoricalDataProvider`
(`provider or AlpacaHistoricalProvider(feed=feed)`) *before* calling
`build_market_data_loop`, then passes that resolved instance both to
`ExecutionService.default(...)` and into `build_market_data_loop`'s own
`provider` parameter — a small, deliberate duplication of the "default
to `AlpacaHistoricalProvider` if `None`" one-liner (matching the
existing `current_git_commit` precedent for accepted small duplication
over premature abstraction), needed so the polling loop and the
execution stage share one provider instance rather than each
independently constructing its own rate limiter and retry policy
against the same Alpaca account. Secrets are validated explicitly, up
front, via `require_valid_runtime(validate_runtime(...))` before any
default `provider`/`broker_adapter` is constructed — mirroring
`build_market_data_loop`'s own internal validation, which would
otherwise run too late here (a default `AlpacaBrokerAdapter`'s own
`TradingClient` construction would surface a missing secret first, as a
less-informative provider-level error, exactly the bootstrap-ordering
trap Phase A caught and fixed for the polling loop itself).

### 4. `RuntimeFrame` gains `order_intent` and `broker_submission_result`

Same pattern as every prior field: `order_intent: OrderIntent | None =
None`, `broker_submission_result: BrokerSubmissionResult | None = None`,
`with_order_intent`/`with_broker_submission_result`,
`require_order_intent`/`require_broker_submission_result`, and two new
`__post_init__` enrichment-order checks (`order_intent` requires
`execution_decision`; `broker_submission_result` requires
`order_intent`).

## Consequences

- The runtime now runs genuinely end to end: `MarketDataLoop ->
  FeatureVectorEmitter -> RegimeEmitter -> StrategyEmitter ->
  OrchestrationEmitter -> RiskEmitter -> ExecutionEmitter ->
  BrokerSubmissionEmitter`, from a bare `Bar` to a submitted (or
  broker-rejected) order. This completes the 7-phase Trading Validation
  runtime roadmap (Phases A-G).
- `ops.metrics.MetricsRegistry` gains its sixth and seventh emitter-level
  production consumers (`ExecutionEmitter`, `BrokerSubmissionEmitter`).
- `ops.checks.execution_adapter_check` (one of Milestone 12's ten
  factories, unused until now) has its first real consumer, wired to
  the broker-submission stage (the stage that actually constructs or
  receives the adapter), not the execution stage.
- No fill handling, trade lifecycle tracking, position reconciliation,
  or memory/experience recording exists anywhere in this runtime yet —
  all explicitly deferred. The natural next increment, whenever
  authorized, is consuming `BrokerSubmissionResult`/`broker_order_id`
  to poll or stream fills and reconcile positions; this ADR does not
  design that.
- A `PipelineResult(frame, stage, success/error)` wrapper — suggested as
  a softer recommendation ("without changing any of the domain
  contracts or `RuntimeFrame` itself") for cleaner logging/metrics/
  replay — is deliberately **not** introduced in this phase. Every
  emitter already logs its own structured success/failure event and
  records its own metrics; no caller in this codebase yet needs a
  uniform cross-stage result object, and building one now would be
  designing ahead of a demonstrated need. Worth revisiting once a real
  consumer (e.g. a replay/observability tool spanning stages) exists.
- `app.bootstrap.__version__`/`app.__version__` bumped `0.6.0` ->
  `0.7.0`.
- No code path in this session invoked real order submission — every
  test exercises `ExecutionEmitter`/`BrokerSubmissionEmitter` with fake,
  in-memory `ExecutionService` providers and a `unittest.mock.MagicMock`
  standing in for `BrokerAdapter`; the one test that constructs a real
  default `AlpacaBrokerAdapter` (proving `execution_service`/
  `broker_adapter` default cleanly) only asserts the loop builds and
  deliberately never calls `on_bar`.

## Alternatives Considered

- **A single `ExecutionEmitter` that both builds and submits the
  order** — rejected per direct instruction: collapsing construction
  and submission into one stage would make it impossible to retry,
  simulate, or swap either concern independently, and would put broker
  I/O behind the same class every backtest/paper-trace tool would need
  to fake just to test order-building logic.
- **A second, independent `paper_trading` flag/config key, separate
  from `AlpacaCredentials.paper`** — rejected: two flags governing the
  same real-vs-paper decision can drift out of sync, and
  `AlpacaCredentials.paper`/`ALPACA_PAPER` already satisfies the
  "default `True`, explicit opt-in to live" requirement for every other
  Alpaca-touching code path in this codebase; introducing a second one
  here would be redundant and a future inconsistency risk, not a safety
  improvement.
- **Refuse to construct a default `BrokerAdapter` at all when
  `credentials.paper` is `False`, forcing an explicit `broker_adapter`
  argument for live trading** — considered, not adopted: the direct
  instruction was to default to paper trading and require an *explicit
  configuration change* (the `ALPACA_PAPER` env var) for live, not to
  additionally gate live trading behind a second, code-level override.
  A loud warning log satisfies "impossible to miss" without adding a
  second gate the instruction didn't ask for.
- **`PipelineResult` wrapper object, built now** — deferred (see
  Consequences) rather than rejected outright; the recommendation was
  explicitly softer ("I would consider") than the two-stage split or
  the paper-trading default, and no consumer in this codebase needs it
  yet.
- **Introduce fill handling / position reconciliation in this same
  phase, since a submitted order is otherwise an unresolved loose
  end** — rejected per direct instruction: explicitly listed as *not*
  in scope for Phase G ("I would not implement: fill handling, trade
  lifecycle, memory updates yet"), and each is substantial enough to
  warrant its own reviewed increment once this phase's submission path
  has been observed working.
