# Changelog

Historical record of what shipped in each tagged version. Never rewritten
after the fact — if a past decision turns out to have been wrong, that's a
new entry (and often a new ADR), not an edit to this one. For where the
project is *headed*, see [PROJECT_STATUS.md](PROJECT_STATUS.md); for *why*
a past decision was made, see
[docs/engineering-handbook/Architecture/ADR/](docs/engineering-handbook/Architecture/ADR/).

Format loosely follows [Keep a Changelog](https://keepachangelog.com/):
each tagged version gets Added / Changed / Known limitations sections.
Versions are tagged per milestone (`vN-<milestone-name>`), not per
semantic-versioning release — this project doesn't ship releases in the
traditional sense yet.

As of 2026-07-13, a second, coarser tag layer also exists —
**umbrella releases** (`v1.0-alpha`, `v1.1-beta`, ...) grouping several
milestone tags for external communication. `v1.0-alpha` points at the
same commit as `v0.7-execution-layer`; it introduces no code of its own
and has no entry below. See [PROJECT_STATUS.md](PROJECT_STATUS.md)'s
"Release Milestones" section for the full grouping and what each
umbrella tag actually points at.

## v0.11 - Signal Orchestration (2026-07-14, tag `v0.11-signal-orchestration`)

### Added
- `src/orchestration/` -- a new, independently packaged platform: the
  first milestone whose purpose is *reconciling* `StrategyDecision`
  (primary), `LearningDecision`, and `NewsSignal` (both advisory) rather
  than producing an independent opinion.
- Built in three explicit phases, each independently verified before the
  next began. Phase A (`arbitration.py`, `signals.py`): `arbitrate` --
  a single, deterministic rule (one disagreement cuts allocation, two
  suppress it entirely) with context validation and agreement
  classification factored into shared helpers from the start. Phase B
  (`interfaces.py`, `policies/`): `ArbitrationPolicy`, a single-method
  Protocol, behind four genuinely distinct mechanisms --
  `SafetyFirstPolicy` (Phase A's original rule, now the default),
  `ConsensusPolicy` (any disagreement suppresses), `WeightedVotePolicy`
  (continuous blend, structurally can never fully suppress as long as
  `strategy_weight > 0`), and `ConfidencePolicy` (scales by relative
  confidence, independent of agreement direction). Phase C
  (`evaluation.py`): `evaluate`/`generate_evaluation_report` --
  agreement rate, signal conflict rate, strategy-vs-learner divergence,
  news alignment, orchestration confidence, override frequency, read
  from paired `(FinalDecision, LearningDecision, NewsSignal)` history.
- `final_allocation` is type-level bounded to `[0.0, primary_allocation]`
  on every policy -- no arbitration mechanism can let an advisory signal
  manufacture conviction the Strategy Engine never had, mirroring
  `ExecutionDecision.approved_allocation`'s bound one layer earlier.
  `outcome` (`CONFIRMED`/`ADJUSTED`/`SUPPRESSED`) is validated against
  the allocation fields at construction, the same discipline
  `ExecutionDecision.decision_type` established.
- `ADR-020-FinalDecision-Contract.md` and
  `ADR-021-Signal-Orchestration-Design.md` -- the `FinalDecision`/
  `SignalInput` contract freeze and this milestone's three-phase
  implementation decisions; binding spec: `Standards/FinalDecision
  Contract.md`.
- 113 new tests: 105 in `tests/orchestration` (models, arbitration, four
  policies, evaluation, performance) plus 8 in `tests/contracts`. 100%
  line/branch coverage on `src/orchestration/`.
- `benchmarks/v0.11-signal-orchestration.json` -- per-policy arbitration
  latency (all four policies, sub-millisecond, pure in-memory).

### Changed
- Nothing in `strategy`, `memory`, `nlp`, `risk`, or `execution` changed
  -- `src/orchestration/` depends on `strategy`/`memory`/`nlp`'s already-
  frozen contracts (reading `StrategyDecision`/`LearningDecision`/
  `NewsSignal`), but none of them gain a new dependency on
  `orchestration`, and `risk` gains no new dependency on it either.

### Known limitations
- Wiring `FinalDecision` into `risk.RiskService` in place of
  `StrategyDecision` remains explicitly not authorized -- the execution
  path still runs on the unarbitrated `StrategyDecision`, exactly as
  every milestone before this one. That wiring is a separate, later,
  explicitly-reviewed decision.
- The four policies' specific parameters (`disagreement_penalty = 0.5`,
  `learner_weight = news_weight = 0.5`, etc.) are reasonable defaults,
  not empirically tuned -- no real arbitration history exists yet to
  tune them against.
- `orchestration.evaluation`'s `strategy_vs_learner_divergence` requires
  the raw `LearningDecision` alongside each `FinalDecision` (not derivable
  from `SignalInput` alone, since `weight`'s meaning differs per policy).

## v0.10 - NLP & Event Processing (2026-07-14, tag `v0.10-nlp-news-engine`)

### Added
- `src/nlp/` -- a new, independently packaged platform: a **shadow-mode-
  only** news signal pipeline that records a `NewsSignal` for every
  processed story, without ever influencing `strategy`, `risk`, or
  `execution`.
- Built in three explicit phases, each independently verified before the
  next began. Phase A (`store.py`, `normalize.py`): `InMemoryNewsItemStore`
  and `JsonlNewsItemStore` -- deterministic ingestion and deduplication on
  `(source, source_id)`, no sentiment model yet; `JsonlNewsItemStore`'s
  `add` is idempotent, writing nothing to disk for a redelivered duplicate.
  Phase B (`sentiment.py`, `service.py`): a batch-only `SentimentScorer`
  Protocol -- no single-headline method exists, architecturally preventing
  the per-headline scoring anti-pattern -- with two implementations:
  `DeterministicSentimentScorer` (dependency-free, used by every Phase B/C
  test) and `FinBertSentimentScorer` (adapts the legacy
  `regime-trader/core/sentiment_engine.py::SentimentEngine`, lazy
  `torch`/`transformers` import so the rest of `nlp` needs zero new
  third-party dependencies). `NlpService.build_signals` assembles the
  frozen `NewsSignal`. Phase C (`evaluation.py`): `evaluate_ingestion`,
  `evaluate_sentiment`, `generate_evaluation_report` -- ingestion latency,
  deduplication rate, sentiment distribution, processing throughput.
  Read-only: no production influence, no state mutation.
- A new `@pytest.mark.integration` marker (alongside the existing
  `performance` marker) for `tests/nlp/test_sentiment_integration.py`,
  which uses `pytest.importorskip` so `FinBertSentimentScorer`'s real
  tests skip gracefully -- not fail -- in any environment (including this
  repository's own base CI matrix) without the `trading` extra installed.
- `ADR-018-NewsSignal-Contract.md` and `ADR-019-NLP-News-Engine-Design.md`
  -- the `NewsSignal` contract freeze (adapting, not porting, the legacy
  FinBERT `SentimentScore` and `NewsItem` shapes, with a new type-level
  `sentiment_label`-matches-argmax check) and this milestone's three-phase
  implementation decisions; binding spec: `Standards/NewsSignal
  Contract.md`.
- 105 new tests (`tests/nlp`) plus 5 in `tests/contracts`, plus 5
  integration tests gated on `torch`/`transformers`. 100% line/branch
  coverage on `src/nlp/` except `FinBertSentimentScorer`'s body (not
  installed in this environment -- see Known limitations).
- `benchmarks/v0.10-nlp-news-engine.json` -- a new benchmark category
  (ingest, dedup check, batch sentiment scoring), all sub-millisecond and
  pure in-memory.

### Changed
- Nothing in `strategy`, `risk`, or `execution` changed -- `src/nlp/`
  gains no new dependency on any of them, and none of them gain a new
  dependency on `src/nlp/`.

### Known limitations
- `FinBertSentimentScorer`'s real behavior is unverified by this
  repository's own CI today -- `torch`/`transformers` (the `trading`
  extra) aren't installed there. The `@pytest.mark.integration` marker
  and `pytest.importorskip` guard make this an honest, visible gap
  (the test file always exists and always attempts to run) rather than a
  silently untested code path.
- Entity extraction is deliberately deferred -- every `NewsSignal`
  produced this milestone has `entities=()`. The frozen contract
  explicitly allows this; a real extractor is future work.
- Deduplication is exact `(source, source_id)` match only -- no fuzzy
  cross-source duplicate detection (the same real story reported by two
  different providers produces two separate `NewsSignal`s today).
- `signal_id` is derived deterministically from `(source, source_id)`,
  which assumes exactly one `NewsSignal` per stored `NewsItem` -- no
  re-scoring or multiple signals per story in this milestone.
- Letting a `NewsSignal` actually influence a real `StrategyDecision`/
  `ExecutionDecision`/`OrderIntent` remains a separate, later,
  explicitly-authorized decision -- that convergence is Milestone 11's
  job (Signal Orchestration), not this one's.

## v0.9 - Adaptive Learning / Memory Loop (2026-07-14, tag `v0.9-memory-loop`)

### Added
- `src/memory/` -- a new, independently packaged platform: a **shadow-mode-
  only** adaptive learning loop that records what it would have
  recommended for every real `StrategyDecision`, without ever influencing
  `strategy`, `risk`, or `execution`. The first package in this handbook
  with zero transitive third-party dependencies.
- Built in three explicit phases, each independently verified before the
  next began. Phase A (`memory.store`): `InMemoryExperienceStore` and
  `JsonlExperienceStore` -- an immutable, append-only Experience Store, no
  learning yet. `JsonlExperienceStore` persists one JSON object per line
  with sorted keys for byte-for-byte deterministic output, and follows
  the load-or-init pattern (a missing file is a legitimate first-run
  state). Phase B (`memory.bandit`, `memory.service`):
  `ThompsonSamplingPolicy`/`BetaArm` -- a contextual multi-armed bandit
  (Thompson Sampling over Beta posteriors, `(strategy_id, regime_id)`
  context) reusing the exact update rule already validated by the legacy
  `regime-trader/core/learning_engine.py`, plus `MemoryService`, the
  sanctioned entry point wiring store and policy together. Phase C
  (`memory.evaluation`): `evaluate`/`generate_evaluation_report` --
  agreement rate, recommendation drift, simulated P&L (linear rescaling
  assumption), cumulative regret, and mean confidence, comparing shadow
  recommendations against realized outcomes. Read-only: no production
  influence, no state mutation.
- `recommended_allocation = production_allocation * sampled_weight` --
  the bandit only ever scales production's own allocation down (or close
  to unchanged for a strong posterior), never proposes a larger
  allocation than production chose, extending invariant #5 (long-only)
  into shadow territory. `confidence = sample_size / (sample_size +
  confidence_smoothing)`, a simpler, more explainable proxy than a
  variance-derived confidence interval.
- `ADR-016-LearningDecision-Contract.md` and `ADR-017-Memory-Loop-Design.md`
  -- the `ExperienceRecord`/`LearningDecision` contract freeze (the first
  contract pair in this handbook adapted from, not ported from, a
  pre-existing legacy implementation) and this milestone's three-phase
  implementation decisions; binding spec: `Standards/LearningDecision
  Contract.md`.
- 114 new tests: 105 in `tests/memory` (models, store, bandit, service,
  evaluation, config, performance) plus 9 in `tests/contracts`. 100% line/
  branch coverage on `src/memory/`.
- `benchmarks/v0.9-memory-loop.json` -- a new benchmark category
  (experience insert, bandit update, recommendation generation), all
  sub-millisecond and pure in-memory.

### Changed
- Nothing in `strategy`, `risk`, or `execution` changed -- `src/memory/`
  gains no new dependency on any of them, and none of them gain a new
  dependency on `src/memory/`. This is the property Milestone 9 exists to
  prove out safely: shadow mode is architectural, not just documented.

### Known limitations
- SHAP-based `rationale` and a LightGBM learning policy are both
  explicitly deferred -- the bandit's posterior summary and a simple,
  non-empty human-readable rationale satisfy this milestone's contract;
  see ADR-016/ADR-017's Alternatives Considered for why.
- The learning context is `(strategy_id, regime_id)` only -- no per-
  symbol, RSI-bucket, or other feature-derived dimension, narrower than
  the legacy design's own context. Widening it is a deliberate, reviewed,
  separately-ADR'd decision, not a natural next increment.
- `evaluation.evaluate`'s `simulated_pnl` uses a linear rescaling
  assumption (realized P&L scaled by the ratio of recommended to
  production allocation) -- not a real counterfactual simulation;
  slippage, liquidity, and risk-limit interactions at a different
  position size are all ignored.
- `JsonlExperienceStore` assumes a single writer per path, with no file
  locking -- matches the legacy `data/trade_context_db.json`'s own
  assumption, not yet revisited for a genuine multi-writer scenario.
- Not yet wired to a real backtest replay or live trading loop as an
  experience producer -- every test in this milestone constructs
  synthetic `ExperienceRecord`s directly.
- Letting a `LearningDecision` actually influence a real
  `StrategyDecision`/`ExecutionDecision`/`OrderIntent` remains a separate,
  later, explicitly-authorized decision -- not something this milestone's
  existence should be read as already permitting.

## v0.8 - Backtesting & Validation (2026-07-13, tag `v0.8-backtesting`)

### Added
- `src/backtest/` -- a new, independently packaged platform: the first
  real consumer of `OrderIntent` (and, transitively, every contract
  before it), replaying historical bars through the *entire* decision
  pipeline (Features -> HMM -> Strategy -> Risk -> Execution) and
  producing the canonical `BacktestResult`. Never retrains models.
  Distinct from the pre-existing, untooled `backtest/` crypto SMA
  sandbox at the repository root.
- Built in two explicit phases: Phase A (`backtest.replay.run_replay`)
  proved deterministic replay to a trade log -- verified with two
  identical runs producing byte-identical output -- *before* a single
  metric was written. Phase B (`backtest.metrics`, `backtest.engine`)
  layered performance metrics and reproducibility metadata on top.
- `backtest.replay.run_replay` -- fills every `OrderIntent` at the
  deciding bar's own open (never the same bar used to make the
  decision), the causal boundary invariant #1 requires. Equity is
  marked at each bar's close, after that step's fills. All symbols
  replay in lockstep at each shared timestamp, so portfolio-level risk
  checks (gross exposure, sector concentration) see every symbol's
  state together; `InsufficientReplayHistoryError` if symbols' bars
  aren't calendar-aligned.
- `backtest.portfolio.PortfolioEngine` -- mutable, stateful cash/position/
  equity tracking, deliberately kept separate from `replay.py` so it can
  be reused for paper trading later. Weighted-average cost basis on
  position top-ups; partial exits keep the remainder open at the
  original average entry price and timestamp.
- `backtest.metrics` -- grouped into `returns` (`cagr`, `sharpe_ratio`,
  `sortino_ratio`, `calmar_ratio`), `risk` (`max_drawdown`), `exposure`
  (`exposure`, `turnover`), and `trade_quality` (`win_rate`,
  `profit_factor`, `average_holding_period`) rather than one large
  module. Degenerate ratios (`calmar_ratio`, `profit_factor`) return
  `float("inf")`, matching `risk.models.PortfolioState.
  gross_exposure_pct`'s existing convention.
- `backtest.engine.BacktestEngine` -- Phase B orchestration: calls
  `run_replay`, computes metrics, assembles `ReplayRun` reproducibility
  metadata (`run_id`, `dataset`, `pipeline_versions` collected from
  every upstream package's own version, `git_commit`, `timestamp`), and
  constructs the frozen `BacktestResult`. `git_commit` is a required,
  explicit input -- `current_git_commit()` is a separate, opt-in helper,
  never invoked implicitly.
- `backtest.reporting.generate_report` -- a minimal, human-readable text
  summary of a `BacktestResult`.
- `ADR-014-BacktestResult-Contract.md` and
  `ADR-015-Backtesting-Engine-Design.md` -- the `BacktestResult` contract
  freeze (the first run-level, not single-event, contract in this
  handbook; embeds a `ReplayRun` reproducibility record added during
  review) and this milestone's implementation decisions; binding spec:
  `Standards/BacktestResult Contract.md`.
- A mandatory golden-dataset regression suite
  (`tests/regression/golden_dataset.py`,
  `tests/regression/baseline_results/synthetic_daily_2024.json`,
  `tests/regression/test_golden_dataset.py`) comparing every CI run
  against a checked-in deterministic synthetic scenario, with a
  documented relative tolerance (not exact equality) given this
  project's own CI matrix runs Python 3.9 and 3.11 against different
  resolved `numpy`/`scipy` versions -- a real, previously observed
  source of cross-version behavioral difference, not a hypothetical one.
- 123 new tests: 101 in `tests/backtest` (models, portfolio, replay
  determinism, metrics incl. degenerate-case boundaries, end-to-end
  engine, config validation) plus 10 in `tests/contracts` and 12 in
  `tests/regression`.
- `benchmarks/v0.8-backtesting.json` -- a single-symbol, one-year
  (252-bar) replay measured at ~2.8s.
- `PROJECT_STATUS.md`'s new "Release Milestones" section and the
  `v1.0-alpha` umbrella tag (grouping Milestones 1-7), declared in the
  same window as this milestone but introducing no code of its own.

### Changed
- Nothing in `regime-trader/` or the pre-existing `backtest/` sandbox
  changed -- `src/backtest/` is not yet wired to any live consumer.

### Known limitations
- Only exercised against deterministic *synthetic* bars (`SYNTH`), never
  real historical equity data -- no live market-data credentials exist
  in this environment (see Known Gaps item 2). Partially, not fully,
  closes Known Gaps item 6: the replay *mechanism* is real, but a
  regime-aware backtest against real historical equity OHLCV still
  needs a live account.
- Fill simulation assumes a full fill at the bar's open with zero
  slippage (`NextBarOpenFillModel`, the only `FillModel` shipped) --
  will overstate performance relative to a real venue's execution
  quality. The `FillModel` Protocol exists specifically so a more
  realistic model can be substituted later without touching `replay.py`.
- `metrics.exposure.exposure` undercounts a position still open at the
  very end of a replay (no `TradeRecord` exists for it yet, only closed
  trades are counted) -- documented in the function's own docstring.
- Multi-symbol replay requires every symbol's bars to share identical
  timestamps (no calendar-alignment/forward-fill support yet) --
  `InsufficientReplayHistoryError` otherwise.

## v0.7 - Execution Layer (2026-07-13, tag `v0.7-execution-layer`)

### Added
- `src/execution/` — a new, independently packaged platform: the first
  real consumer of `ExecutionDecision`, converting it (with current
  `PortfolioState`) into the canonical `OrderIntent` (`timestamp`,
  `symbol`, `side`, `quantity`, `order_type`, `limit_price`,
  `time_in_force`, `reference_price`, `stop_loss`, `take_profit`,
  `idempotency_key`, `reasoning`, `execution_reference`, `metadata`) --
  broker-agnostic: every field type is first-party, never an Alpaca SDK
  type.
- `execution.router.route` -- reconciles `ExecutionDecision.
  approved_allocation` (a target fraction of equity) against the
  existing position for that symbol to decide buy/sell/hold and a
  whole-share quantity. Neither `StrategyDecision` nor `ExecutionDecision`
  expresses an order delta directly; this is genuinely new logic, not a
  port. A `SELL` quantity is capped at an approximate current share
  count (`market_value / reference_price`), documented as an
  approximation rather than an exact guarantee.
- `execution.models.ExecutionContext`/`FeatureSnapshot` -- internal,
  deliberately *unfrozen* value objects carrying a transient market
  observation (price) and the minimal feature slice
  (`atr_14`/`realized_volatility_20`) a stop-loss policy needs. Per
  ADR-012's amended principle ("execution contracts describe trading
  intent, not market observations"), neither is a frozen contract and
  neither is embedded in `OrderIntent`.
- `execution.interfaces.{MarketSnapshotProvider,FeatureSnapshotProvider,
  StopLossPolicy,BrokerAdapter}` -- four pluggable `Protocol`s.
  `BrokerAdapter` is kept structurally separate from `ExecutionService`:
  building an `OrderIntent` and submitting one are different operations
  with different failure modes.
- `execution.stop_loss.{ATRStopPolicy,FixedPercentPolicy}` -- pluggable
  stop-loss sizing. `ATRStopPolicy` (the default) sets a stop
  `atr_multiplier` average-true-ranges below the reference price;
  `FixedPercentPolicy` is a fallback ignoring volatility entirely. No
  concrete "volatility tier" formula exists anywhere in this codebase to
  port, so both are new designs grounded in `src/features`'s existing
  ATR feature, not a port of unfound legacy logic.
- `execution.providers.{BarSnapshotProvider,FeaturePipelineSnapshotProvider}`
  -- concrete provider implementations wrapping `market_data.interfaces.
  HistoricalDataProvider` and `features.FeaturePipeline`. Never import a
  specific provider (`AlpacaHistoricalProvider`) or `alpaca-py` directly.
  `BarSnapshotProvider` is honest about what a `Bar`-only data source
  can't supply: `bid`/`ask`/`spread` are always `None`.
- `execution.order_builder.OrderBuilder` / `execution.execution_service.
  ExecutionService` -- orchestration. `ExecutionService.default(
  historical_provider)` wires a sensible default pipeline (bar-close
  snapshots, `FeaturePipeline`-computed features, `ATRStopPolicy`).
- `execution.broker_adapter.AlpacaBrokerAdapter` -- the *only* module
  under `src/execution/` that imports `alpaca-py`. Translates an
  `OrderIntent` into a real OTO/BRACKET `MarketOrderRequest`, matching
  `regime-trader/broker/order_executor.py`'s existing construction logic
  (ported, not reimplemented from scratch) but consuming `OrderIntent`
  instead of raw `entry_price`/`stop_price`/`notional_value` parameters.
  Whole-share quantity and the mandatory-stop-for-a-BUY rule are already
  guaranteed by `OrderIntent`'s own construction-time invariants by the
  time an intent reaches this adapter -- no re-validation needed.
- `execution.retry.submit_with_retry` -- bridges `BrokerAdapter.
  submit_order`'s result-based failure (it never raises, matching
  `OrderExecutor`'s existing pattern) into `common.retry.call_with_retry`'s
  exception-based mechanism. Every retry resubmits the same `OrderIntent.
  idempotency_key` as `client_order_id` -- a real improvement over the
  legacy `order_executor.py`, whose per-call `uuid.uuid4()` could not
  have supported genuine idempotent retries.
- `ADR-012-OrderIntent-Contract.md` and
  `ADR-013-Execution-Layer-Design.md` -- the `OrderIntent` contract
  freeze (including the "execution contracts describe trading intent,
  not market observations" principle, added during review before
  implementation began) and this milestone's implementation decisions;
  binding spec: `Standards/OrderIntent Contract.md`.
- `execution` extras group in `pyproject.toml` (pandas, numpy,
  `alpaca-py`) -- the first milestone-5-onward package with a real
  third-party dependency of its own, scoped to the one module
  (`broker_adapter.py`) that actually needs it.
- 85 new tests: 74 in `tests/execution` (routing buy/sell/hold/no-action,
  stop-loss policies, order building incl. a non-protective-stop guard,
  concrete providers against a fake `HistoricalDataProvider`, broker
  translation against a mocked `TradingClient`, retry/idempotency,
  end-to-end `ExecutionService` wiring) plus 11 in `tests/contracts`.
- `benchmarks/v0.7-execution-layer.json` -- `ExecutionService.decide`
  latency (~0.017ms/call over 10,000 trials against fake in-memory
  providers; excludes real bar-fetch/feature-computation cost).

### Changed
- Nothing in `regime-trader/` changed -- `broker/order_executor.py`
  remains untouched; `src/execution/` is not yet wired to any live
  consumer.

### Known limitations
- `OrderType.LIMIT` is modeled in the frozen contract but has no broker
  translation yet -- `AlpacaBrokerAdapter.submit_order` raises
  `NotImplementedError` for one. No current requirement or legacy
  precedent calls for a limit order.
- No live bid/ask: `BarSnapshotProvider` always reports `bid=ask=spread=
  None` -- a `Bar` carries no quote data. A `MarketSnapshotProvider`
  backed by `market_data.interfaces.StreamingDataProvider`'s live quotes
  is future work.
- `DEFAULT_TICK_SIZE = 0.01` is a flat placeholder for all US equities,
  not a real venue-specific tick table.
- `router.py`'s `SELL` quantity cap
  (`current_position_value / reference_price`) is an approximation --
  `Position.market_value` is a dollar mark-to-market figure, not a
  stored share count, the same documented caveat `core/risk_manager.py`'s
  `ProposedTrade.dollar_risk` already carries.
- Only exercised against synthetic `ExecutionDecision`/`PortfolioState`
  pairs and fake providers -- not yet run end-to-end against real
  historical data or a real (even paper) Alpaca account.

## v0.6 - Risk Management (2026-07-13, tag `v0.6-risk-management`)

### Added
- `src/risk/` — a new, independently packaged platform: the first real
  consumer of `StrategyDecision`, converting it (with a `PortfolioState`/
  `AccountState` snapshot) into the canonical `ExecutionDecision`
  (`timestamp`, `symbol`, `approved`, `approved_allocation`,
  `decision_type`, `risk_adjustments`, `reasoning`, `strategy_reference`,
  `metadata`). A packaged, hardened port of `regime-trader/core/
  risk_manager.py`'s veto layer, not a from-scratch build.
- `risk.models.DecisionType` — explicit `APPROVED`/`REDUCED`/`REJECTED`
  classification, added during contract review, cross-checked against
  `approved`/`approved_allocation`/`risk_adjustments` at construction.
- `risk.validators` — small, composable, one-concern-each validators
  ported from `core/risk_manager.py::check_exposure_limits`
  (`GrossExposureValidator`, `LeverageValidator`,
  `SingleTickerExposureValidator`, `SectorExposureValidator`) plus a net
  new `BuyingPowerValidator` (`AccountState` has no legacy precedent).
  `LiquidityValidator` ships as a deliberate `NotImplementedError`
  placeholder (Master Charter invariant #4) — no volume/spread data
  exists in any current input.
- `risk.sizing.ExposureCapacitySizing` — a new, reduce-only sizing rule
  with no legacy equivalent: fits a decision's allocation to remaining
  gross-exposure/single-ticker/sector headroom instead of rejecting it
  outright. `RiskService.default()` uses this, not the four exposure
  validators above, as its default policy for those concerns — see the
  redundancy bug below.
- `risk.circuit_breakers.DrawdownCircuitBreaker` — ported from
  `core/risk_manager.py::evaluate_circuit_breakers`: the same drawdown
  tiers, most-severe-first evaluation, and disk-backed emergency
  hard-stop lock file (never programmatically deleted, per Master
  Charter invariant #3).
- `risk.service.RiskService` — the package's single entry point:
  `StrategyDecision -> validators -> sizing -> circuit breakers ->
  ExecutionDecision`. `RiskService.default()` assembles a sensible
  default pipeline; a caller wanting the legacy module's zero-tolerance
  exposure policy constructs `RiskService` directly with the four
  exposure validators instead.
- `ADR-010-ExecutionDecision-Contract.md` and
  `ADR-011-Risk-Manager-Design.md` — the `ExecutionDecision` contract
  freeze (landed ahead of this tag, ungoverned by it, later amended
  during review to add `decision_type`) and this milestone's
  implementation decisions: the validator/sizing redundancy bug and its
  fix, the validators→sizing→circuit-breakers pipeline order and why
  it's outcome-equivalent to the legacy order, float-precision handling
  for `decision_type`, minimal `AccountState`, and what's deliberately
  deferred (per-trade dollar risk, correlation filtering, real
  liquidity); binding spec: `Standards/ExecutionDecision Contract.md`.
- 102 new tests: 87 in `tests/risk` (boundary tests for every threshold,
  approval/rejection/reduction paths, multiple simultaneous violations,
  circuit-breaker activation and most-severe-first ordering, the
  emergency lock file's idempotency, determinism, validator/sizing
  composition, an `InvalidSizingResultError` regression test) plus 12 in
  `tests/contracts/test_executiondecision_contract.py`; `src/risk/`
  reaches 100% line and branch coverage.
- `benchmarks/v0.6-risk-management.json` — `RiskService.decide` latency
  (~0.026ms/call over 10,000 trials), comfortably under the milestone's
  <1ms target.

### Changed
- Nothing in `regime-trader/` changed — `core/risk_manager.py` remains
  the live risk-veto path; `src/risk/` is not yet wired to any consumer.

### Known limitations
- A real design bug was found via testing, not caught in review before
  implementation: the first cut wired all four exposure/leverage
  validators into `RiskService.default()` alongside
  `ExposureCapacitySizing`, both checking the identical ratio against
  the identical threshold — meaning any decision sizing would have
  reduced was instead always rejected outright first, making
  `DecisionType.REDUCED` structurally unreachable in the default
  pipeline. Fixed by excluding those four validators from
  `RiskService.default()` (they remain fully implemented and tested for
  a caller wanting the stricter, zero-tolerance policy instead). See
  ADR-011 Decision 1.
- Per-trade dollar-risk and correlation-filter checks from
  `core/risk_manager.py` were not ported — both need data
  (`entry_price`/`stop_price`, a rolling return history) that isn't part
  of `StrategyDecision`, `PortfolioState`, or `AccountState` in this
  milestone's pipeline. Both remain real, working checks in the still-live
  `core/risk_manager.py`; nothing regresses in production. See ADR-011
  Decision 5.
- `LiquidityValidator` has no real implementation — it raises
  `NotImplementedError` unconditionally and is never wired into
  `RiskService.default()`. See ADR-011 Decision 6.
- Only exercised against synthetic `StrategyDecision`/`PortfolioState`/
  `AccountState` triples constructed directly in tests — not yet run
  end-to-end against a real `StrategyService.decide` output.
- `RiskService.default()`'s policy (graceful reduction over hard
  rejection for gross/single-ticker/sector exposure) is more permissive
  than `core/risk_manager.py`'s original binary-reject behavior — a
  deliberate product decision, not an oversight; see ADR-011 Decision 1
  for the full reasoning and how to opt into the stricter policy instead.

## v0.5 - Strategy Engine (2026-07-12, tag `v0.5-strategy-engine`)

### Added
- `src/strategy/` — a new, independently packaged platform: the first real
  consumer of `RegimeState`, converting `RegimeState` (with `FeatureVector`
  as context) into the canonical `StrategyDecision` (`timestamp`, `symbol`,
  `strategy_id`, `regime_id`, `allocation`, `confidence`,
  `expected_holding_period`, `reasoning`, `metadata`). Scoped strictly to
  selecting a strategy and expressing allocation intent — no capital/
  liquidity/leverage checks, no order placement, no broker/risk/memory/NLP
  integration.
- `strategy.interfaces.Strategy` — a `Protocol` with `supports(regime_id)`
  and `allocate(feature_vector, regime_state) -> StrategyDecision`.
- `strategy.registry.StrategyRegistry` — dispatch driven entirely by each
  registered strategy's own `supports()` method, with no separate
  `regime_id -> strategy_id` map to drift out of sync; raises
  `UnsupportedRegimeError` on zero matches (unless a `default_strategy_id`
  fallback is configured) and `AmbiguousStrategyError` on more than one.
- `strategy.strategies.{bull,bear,sideways,defensive}` — four reference
  strategies (`create_growth_strategy`, `create_bear_strategy`,
  `create_mean_reversion_strategy`, `create_defensive_strategy`) built on
  a shared `RegimeMappedStrategy`: `allocation = base_allocation *
  regime_state.confidence`, `confidence = regime_state.confidence`
  directly. None hardcode which `regime_id` values they apply to —
  `supported_regime_ids` is always caller-supplied per trained model (see
  ADR-009 Decision 4).
- `strategy.service.StrategyService` — the package's single entry point:
  resolves a strategy via the registry, then calls `allocate`.
  `StrategyEngineConfig.default_strategy_id` is an explicit opt-in
  fallback (`None` by default — fails loudly on an unmapped regime until
  an operator deliberately configures one).
- `ADR-008-StrategyDecision-Contract.md` and
  `ADR-009-Strategy-Engine-Design.md` — the `StrategyDecision` contract
  freeze (landed ahead of this tag, ungoverned by it) and this milestone's
  implementation decisions: `supports()`-only dispatch, the fallback-vs-
  direct-dispatch bug found and fixed during smoke testing, the
  confidence-propagation formula, and caller-supplied `regime_id`
  semantics; binding spec: `Standards/StrategyDecision Contract.md`.
- `to_dict`/`from_dict` on `FeatureVector`, `Provenance`, and `RegimeState`
  (previously only `hmm.models.ModelMetadata` had them) — additive, no
  contract version bump, added to support this milestone's new
  `tests/contracts/` requirement.
- `tests/contracts/` — a new cross-package regression suite (distinct from
  each package's own unit tests) verifying `FeatureVector`, `RegimeState`,
  and `StrategyDecision` each have exactly their frozen field set, correct
  version metadata, lossless `to_dict`/`from_dict` round-trips, and
  documented backward-compatibility behavior (unknown metadata keys
  tolerated, invariant violations rejected).
- 83 new tests: 55 in `tests/strategy` (registry resolution, unsupported-
  regime/ambiguous-match/fallback-to-default paths, confidence propagation
  and allocation-bounds across a base×confidence grid, deterministic
  output, configuration overrides, service dispatch, a dedicated
  regression test for the fallback-dispatch bug fix) plus 28 in
  `tests/contracts`.
- `benchmarks/v0.5-strategy-engine.json` — `StrategyService.decide`
  latency (~0.0096ms/call over 10,000 trials), comfortably under the
  milestone's <1ms target and, expectedly, several orders of magnitude
  cheaper than `hmm.service.RegimeService.infer`'s ~20.9ms (v0.4) since
  this milestone adds no computation heavier than a dict/set lookup and a
  multiplication.
- `common.time.require_utc` consolidation completed: `market_data.models`
  and `features.feature_vector` now both import the shared helper (already
  used by `hmm.models` since v0.4) instead of each independently
  reimplementing the same UTC check.

### Changed
- Nothing in `regime-trader/` changed — `core/regime_strategies.py` (not
  yet built there) remains a gap; `src/strategy/` is not yet wired to any
  consumer.

### Known limitations
- No tooling exists yet to help an operator determine which `regime_id`
  is "bull-like" for a freshly trained HMM (e.g. inspecting
  `GaussianHMM.means_` per fitted component) — `supported_regime_ids` must
  currently be derived by hand per trained model. See ADR-009 Decision 4.
- Confidence and allocation are a single linear formula off `RegimeState.
  confidence` alone — no independent signal (sentiment, bandit confidence)
  factors in yet; combining future signal sources is an open design
  question for whichever milestone introduces them, not decided here. See
  ADR-009 Decision 3.
- Only exercised against synthetic `FeatureVector`/`RegimeState` pairs
  constructed directly in tests — not yet run end-to-end against a real
  `RegimeService.infer` output.
- No portfolio construction or optimization across multiple symbols —
  `StrategyService.decide` operates on one `(FeatureVector, RegimeState)`
  pair at a time, by design (deferred, not an oversight).

## v0.4 - HMM & Regime Detection (2026-07-12, tag `v0.4-hmm-regime-detection`)

### Added
- `src/hmm/` — a new, independently packaged platform: `hmm.service.
  RegimeService`, a deterministic Gaussian HMM engine consuming only
  `FeatureVector` and producing only the canonical `RegimeState`
  (`timestamp`, `symbol`, `regime_id`, `confidence`,
  `transition_probability`, `model_version`, `feature_pipeline_version`,
  `metadata`).
- `hmm.normalizer.ZScoreNormalizer` — deterministic per-feature
  normalization with explicit missing-value handling (`drop_incomplete_
  rows`; never silent imputation).
- `hmm.trainer`/`hmm.selector` — Baum-Welch/EM training with configurable
  state count, covariance type, and random seed (multiple restarts,
  highest-log-likelihood kept), plus BIC+AIC model selection over a
  configurable candidate state range — both criteria always computed and
  recorded regardless of which one drives selection.
- `hmm.inference.forward_algorithm` — the causal Forward Algorithm
  (`P(S_t | X_{1:t})`), ported from `regime-trader/core/hmm_engine.py`;
  `GaussianHMM.predict_proba`/`.predict`/`.decode` are never called
  anywhere in this package.
- `hmm.persistence` — filesystem artifact save/load (`model.pkl`,
  `normalizer.pkl`, `metadata.json`), versioned per symbol.
- Hard-fail feature-version drift detection: `RegimeService.infer`/
  `infer_series` refuse to run if a `FeatureVector`'s
  `provenance.feature_versions` doesn't match what the loaded model was
  trained on — the direct payoff of Milestone 3's `Provenance` addition
  (v0.3.x, ADR-005).
- `ADR-006-RegimeState-Contract.md` and `ADR-007-HMM-Design.md` — the
  `RegimeState` contract freeze and the modeling/engineering decisions
  behind `src/hmm/`; binding spec: `Standards/RegimeState Contract.md`.
- `hmm` extras group in `pyproject.toml` (pandas, numpy, scipy, hmmlearn),
  depending on `features.feature_vector`/`features.pipeline` at import
  time but never on `market_data` directly.
- `common.time.require_utc` — a shared UTC-timestamp validation helper,
  promoted out of three independent copies of the same check
  (`market_data.models.Bar`, `features.feature_vector`, and now
  `hmm.models.RegimeState`).
- 91 tests for `src/hmm` (unit, integration, quantitative regime-
  switching/stability/noise/constant-series/missing-value scenarios,
  reproducibility, and performance), plus one true end-to-end integration
  test running real `Bar`s through `FeaturePipeline` into `RegimeService`.
- `benchmarks/` — one JSON snapshot per tagged milestone (timing +
  peak-RSS memory), so performance regressions are diffable against
  history instead of re-derived from old PR descriptions. Includes a
  backfilled `v0.3-feature-engineering.json` alongside this tag's own
  `v0.4-hmm-regime-detection.json`.
- As a prerequisite landed in this same tag: `FeatureVector` contract v2
  — a required `provenance: Provenance` field (`pipeline_version`,
  `manifest_version`, `feature_versions`, `generated_at`,
  `source_dataset`), replacing the old duplicated `version`/
  `metadata["pipeline_version"]`/`metadata["source"]` fields (ADR-004,
  ADR-005; binding spec: `Standards/FeatureVector Contract.md`).

### Changed
- Nothing in `regime-trader/` changed — `core/hmm_engine.py` remains the
  live regime-detection path; `src/hmm/` is not yet wired to any consumer
  or to `main.py.ModelStore` (deliberate — see ADR-007 Decision 7).

### Known limitations
- Only exercised against synthetic `FeatureVector`s and real
  `FeaturePipeline` output over synthetic bars — no model in this
  milestone has been trained or run against real historical or live
  market data.
- Single-inference latency measured at ~20ms over a 252-bar window, not
  the originally-targeted <5ms — that target assumed an incremental,
  O(1)-per-call live filter (`hmm_engine.py`'s `ForwardFilter`) that this
  milestone deliberately didn't build; `RegimeService.infer` re-runs the
  batch Forward Algorithm over the full supplied window every call
  instead. See ADR-007 Decision 7.
- `main.py.ModelStore.get_model(ticker) -> GaussianHMM` is incompatible
  with `RegimeService`'s "never expose `hmmlearn` internals" rule and is
  not satisfied by this milestone — reconciling the two is left to
  whichever milestone first wires a real consumer to `src/hmm/`.
- A real bug (`scipy.stats.multivariate_normal.logpdf` raising on a
  singular covariance matrix, reproduced by a constant-valued feature)
  was found and fixed in `src/hmm/inference.py`
  (`allow_singular=True`); the identical, unfixed exposure in the ported-
  from `regime-trader/core/hmm_engine.py` is flagged as a follow-up, not
  fixed in this change.
- `ModelMetadata.feature_versions` snapshots only the *last* row of the
  training window, not the whole window — a feature-formula change that
  lands mid-training-window isn't separately detected.

## v0.3 - Feature Engineering Platform (2026-07-12, tag `v0.3-feature-engineering`)

### Added
- `src/features/` — a new, independently packaged platform: registry-
  backed causal feature library (39 features across price, volatility,
  trend, volume, market structure, statistical, and regime categories),
  `FeaturePipeline` (validation → cleaning → corporate-action adjustment →
  feature computation → output validation), and a canonical
  `FeatureVector(timestamp, symbol, feature_values, feature_names,
  metadata, quality_flags, version)` output type every downstream
  consumer is meant to read.
- `FeatureRegistry` / `@feature(...)` decorator — every registered feature
  enforces `uses_future_data=False` at construction (no opt-out), and a
  registry-driven perturbation test (`test_no_lookahead_all_features.py`)
  proves causality automatically for every feature without a per-feature
  test being hand-written.
- `config/feature_manifest.yaml` — a generated-but-checked-in, machine-
  readable feature catalog (name, category, version, lookback, dtype,
  description, `uses_future_data`, `depends_on`), regenerated from the
  registry via `features.manifest.write_manifest` and kept fresh by a
  dedicated test.
- `features` extras group in `pyproject.toml` (pandas, numpy, ta),
  depending on `market_data.models`/`market_data.validation` at import
  time but not on `market_data`'s heavier storage/provider dependencies.
- `ADR-003-Feature-Engineering.md` — key decisions: canonical
  `FeatureVector`, registration-time leakage protection, reuse of
  `market_data.validation` rather than re-implementing bar cleaning,
  confirmed/lagged reporting for market-structure signals, the manifest,
  and what was deliberately deferred (cross-symbol correlation, `main.py`
  wiring).
- 199 tests for `src/features`, covering per-category correctness,
  registry/`FeatureVector` contract behavior, the pipeline, output
  validation, the manifest, the explicit Milestone 3 edge-case checklist
  (NaNs, missing bars, duplicate timestamps, timezone/DST transitions,
  stock splits, insufficient history, constant prices, extreme
  volatility), and measured performance against the milestone's targets.

### Changed
- Nothing in `regime-trader/` changed — `data/feature_engineering.py`
  remains the live feature path for the existing HMM; `src/features` is
  not yet wired to any consumer (deliberate, per this milestone's scope —
  see Milestone 4).

### Known limitations
- Only exercised against a deterministic synthetic bar generator
  (`tests/features/conftest.py::make_bars`) — no feature in this registry
  has yet been run against real historical or live data pulled through
  `market_data`'s Alpaca providers.
- `hurst_exponent_100` is, by a wide margin, the most computationally
  expensive feature in the registry (~2.6s for a 21-trading-day, 1-minute-
  bar run) and is excluded from the platform's recommended 1-minute-bar
  feature subset on conventional-use grounds (a 100-bar window covers
  under two trading hours at that granularity) — see `test_performance.py`
  and ADR-003's Verification note.
- The "Regime" category ships two features (`liquidity_proxy_20`,
  `volatility_clustering_20`), not the originally-scoped cross-symbol
  "correlation changes" feature — every feature here is a pure function of
  one symbol's own bar history; a cross-symbol feature needs a design this
  milestone deliberately didn't make (see ADR-003 Decision 6).
- Two real bugs in the third-party `ta` library (`ADXIndicator.adx()` and
  `AverageTrueRange.average_true_range()` both raising an unguarded
  `IndexError`, not a graceful NaN, below their true minimum input length)
  were found and worked around with explicit length guards — not fixed
  upstream.

## v0.2 - Market Data Platform (2026-07-12, tag `v0.2-market-data`)

### Added
- `src/market_data/` — a new, independently packaged platform: provider-
  agnostic domain models (`Bar`, `Trade`, `Quote`, `OrderBook`, `Snapshot`,
  `CorporateAction`), `Protocol`-based provider interfaces
  (`HistoricalDataProvider`, `StreamingDataProvider`,
  `CorporateActionsProvider`, `MarketDataStorage`).
- Alpaca historical provider (paginated internally by the SDK, retried via
  `common.retry`, rate-limited) and Alpaca streaming provider (custom
  reconnect-with-backoff loop, heartbeat staleness detection, per-message
  latency tracking).
- Parquet-backed storage (`ParquetBarStore`) doubling as local cache and
  incremental-update mechanism, plus a DuckDB SQL query layer
  (`DuckDBBarQuery`) for cross-symbol analytics.
- Validation: missing-bar detection, duplicate-timestamp handling,
  timezone normalization, corporate-action split adjustment.
- `HistoricalReplay` — sync iteration for backtesting, paced async replay
  for exercising streaming consumers against historical data.
- `regime-trader/broker/alpaca_client.py` — a thin adapter satisfying
  `main.py.MarketDataProvider`, closing Known Gaps item 2.
- `market-data` extras group in `pyproject.toml` (pandas, numpy, pyarrow,
  duckdb, alpaca-py), independent of the `trading` extra.
- `docs/engineering-handbook/Architecture/ADR/` — the ADR process itself
  (`README.md`, `TEMPLATE.md`), plus `ADR-001-Foundation.md` (retroactively
  documenting Milestone 1's decisions) and `ADR-002-Market-Data.md`.
- `PROJECT_STATUS.md` — the live milestone dashboard.
- 168 tests for `src/market_data` and the `regime-trader` adapter contract
  (97% coverage).

### Changed
- `regime-trader/main.py` now constructs `AlpacaMarketDataClient()` in
  place of the `_NotYetImplemented("broker/alpaca_client.py ...")`
  placeholder — a two-line diff; no other line in `regime-trader/` changed.
- MyPy/Ruff/Black scope extended by exactly one file:
  `regime-trader/broker/alpaca_client.py` is now checked alongside `src/`
  and `tests/`; the rest of `regime-trader/` remains outside this
  repository's own tooling (tracked in Known Gaps.md).

### Known limitations
- Not exercised against a live Alpaca account — no credentials available
  in the environment this was built in. SDK usage (request/response
  shapes, method signatures) was verified by inspecting the actually-
  installed `alpaca-py==0.43.5` package directly, not by a live API call.
- `DAY_1` gap detection in `validation.find_missing_bars` only accounts
  for weekends, not market holidays (no trading-calendar dependency yet).
- Corporate-actions handling covers splits and cash dividends; mergers,
  spinoffs, and other action types are parsed but silently skipped (logged
  at debug level).

## v0.1 - Foundation (2026-07-12, tag `v0.1-foundation`)

### Added
- `pyproject.toml` — PEP 621 packaging, dependency groups (`dev`,
  `trading`), Ruff/Black/MyPy/Pytest configuration.
- `src/common/` — the foundation package: `Settings` (pydantic-settings,
  env + `.env` file, safe-by-default `environment`), structured JSON/
  console logging (`configure_logging`), base interfaces (`Clock`,
  `Service`, `HealthCheck`), and utilities (`SystemClock`/`FixedClock`,
  `RetryPolicy`/`call_with_retry`, `atomic_write_json`/
  `read_json_or_default`, an `AppError` exception hierarchy).
- `Dockerfile` + `docker-compose.yml` — multi-stage build, non-root user,
  healthcheck; runs `python -m common`'s smoke-test entrypoint.
- `.github/workflows/ci.yml` — lint, typecheck, test (Python 3.9 + 3.11
  matrix), Docker build.
- `.pre-commit-config.yaml`, `.env.example`, `config/app.example.yaml`,
  `.gitignore`.
- Root `README.md`.
- 49 tests for `src/common` (99% coverage).

### Changed
- Repository initialized under git (`git init`) for the first time.

### Known limitations
- `regime-trader/` and `backtest/` are deliberately untouched and remain
  outside this repository's own Ruff/Black/MyPy/CI coverage — see the
  tooling-scope note in
  [Architecture/Known Gaps.md](docs/engineering-handbook/Architecture/Known%20Gaps.md).
- `requires-python = ">=3.9"` reflects the newest interpreter available in
  the environment this was built in, not a deliberately chosen floor —
  see `pyproject.toml`'s note on raising it later.
- Local verification ran on Python 3.9.6; CI targets 3.9 and 3.11, but the
  3.11 path was not exercised locally before this tag.
