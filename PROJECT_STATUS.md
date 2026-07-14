# Project Status

Live dashboard of milestone progress for Regime Trader. This file is the
fast answer to "where are we"; for the *why* behind any of it, see
[docs/engineering-handbook/00_MASTER_CHARTER.md](docs/engineering-handbook/00_MASTER_CHARTER.md)
(the constitution this roadmap operates under),
[docs/engineering-handbook/Architecture/Known Gaps.md](docs/engineering-handbook/Architecture/Known%20Gaps.md)
(what's built vs. missing at the component level), and
[docs/Compatibility.md](docs/Compatibility.md) (which contract/package
version each component was built and verified against).

**Last updated**: 2026-07-14 · **Current milestone**: 10 — NLP & Event Processing (not yet started)

**Architecture Complete as of `v0.4-hmm-regime-detection`**: not feature
complete, but the core data flow now exists end to end — Market Data →
Feature Pipeline → `FeatureVector` → HMM → `RegimeState` — with every
producer/consumer boundary in that chain a frozen, versioned contract
(`FeatureVector` v2, `RegimeState` v1). Every remaining milestone
(Strategy Engine onward) builds on this pipeline rather than reaching
past it; see [docs/Compatibility.md](docs/Compatibility.md) for the exact
versions.

**Decision + Execution pipeline complete as of `v0.7-execution-layer`**:
the full chain now runs end to end — Market Data → Features →
`FeatureVector` → HMM → `RegimeState` → Strategy Engine →
`StrategyDecision` → Risk Manager → `ExecutionDecision` → Execution
Layer → `OrderIntent` → `BrokerAdapter` → Alpaca — every boundary a
frozen, versioned contract (see [docs/Compatibility.md](docs/Compatibility.md)).
Not yet wired to a live account and not yet validated against real
historical data (Milestone 8's job); this note marks architectural
completeness of the decision-and-execution path, not production
readiness.

## Release Milestones (umbrella releases)

Grouping releases spanning multiple implementation milestones — a
coarser-grained view for external communication than the per-milestone
`vN-<name>` tags below, which remain the authoritative, individually
tagged record and are never replaced or superseded by these. An umbrella
tag (e.g. `v1.0-alpha`) points at the same commit as the last milestone
tag it groups (`v0.7-execution-layer`); it exists purely as a label over
already-tagged history.

| Release | Includes | Status |
|---|---|---|
| `v1.0-alpha` | Milestones 1–7 (end-to-end paper-trading-ready architecture: Foundation through Execution Layer) | ✅ Tagged |
| `v1.1-beta` | Milestone 8 (Backtesting & Validation) | 🚧 Milestone tagged (`v0.8-backtesting`); umbrella tag not yet cut |
| `v1.2-beta` | Milestone 9 (Adaptive Learning / Memory Loop) | 🚧 Milestone tagged (`v0.9-memory-loop`); umbrella tag not yet cut |
| `v1.3-rc` | Milestone 10 (NLP News Engine) | ⏳ Planned |
| `v1.4-rc` | Milestone 11 (Signal Orchestration) | ⏳ Planned |
| `v2.0` | Milestone 12 (Production Monitoring & Deployment) | ⏳ Planned |

"Alpha"/"beta"/"rc" here describe validation maturity, not code
stability in the traditional semver sense: `v1.0-alpha` is architecturally
complete but unvalidated against real historical data and unrun against
a live account; each subsequent umbrella release adds a layer of
validation or capability without the earlier layers being revisited
just to earn the label.

**Roadmap revision (2026-07-12)**: milestones 3–10 below were restructured
from the original plan after Milestone 2's retro. Two changes: (1) a
dedicated Feature Engineering Platform milestone now sits between Market
Data and HMM, so the HMM consumes a normalized `FeatureVector`, never raw
bars, directly — see the "Feature pipeline" note under Milestone 3; (2)
the former single "Strategies" milestone is split into **Strategy Engine**
(regime-tier allocation logic, Milestone 5) and **Signal Orchestration**
(final cross-source arbitration, Milestone 11, moved later since it
depends on every other signal source existing first). See
[CHANGELOG.md](CHANGELOG.md) for what shipped under the original numbering
in v0.1/v0.2 — this file's milestone numbers describe what's ahead, not a
renumbering of history.

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | Complete — merged, verified, tagged |
| 🚧 | In progress |
| ⏳ | Planned — not started |
| ⚠️ | Blocked |

## Milestones

| # | Milestone | Status | Scope | Notes |
|---|---|---|---|---|
| 1 | Foundation | ✅ Complete | Packaging (`pyproject.toml`), dependency management, `src/common/` (config, structured logging, base interfaces, utilities), Docker/Compose, GitHub Actions CI, Ruff/Black/MyPy/Pytest, pre-commit. No trading logic. | Tagged `v0.1-foundation`. Key decisions (Protocols, Pydantic, strict MyPy, DI, the `[trading]` extra, why `regime-trader/` wasn't touched): [ADR-001-Foundation](docs/engineering-handbook/Architecture/ADR/ADR-001-Foundation.md). Tooling is scoped to `src/`+`tests/` only — see Known Gaps.md's "Tooling scope" note. |
| 2 | Market Data | ✅ Complete | Provider interfaces, provider-agnostic models (Bar/Trade/Quote/OrderBook/Snapshot/CorporateAction), Alpaca historical + streaming providers, retry/rate-limiting, Parquet+DuckDB storage with incremental updates, validation (missing bars/duplicates/timezone/split adjustment), replay harness. 168 tests, 97% coverage. | Tagged `v0.2-market-data`. Closed Known Gaps item 2 — `regime-trader/broker/alpaca_client.py` is now a real adapter over `src/market_data`, wired into `main.py`. Key decisions (new package vs. `regime-trader/broker/`, Protocol interfaces, Parquet+DuckDB, the `[market-data]` extra, the adapter pattern, custom reconnect/heartbeat): [ADR-002-Market-Data](docs/engineering-handbook/Architecture/ADR/ADR-002-Market-Data.md). Not exercised against a live Alpaca account — no credentials available; SDK usage verified against the installed `alpaca-py` package instead. |
| 3 | Feature Engineering Platform | ✅ Complete | Registry-backed causal feature pipeline: 39 features across price (returns, momentum, gaps), volatility (ATR, realized/Parkinson/Garman-Klass, rolling std), trend (EMA/SMA/MACD/ADX/RSI/slope), volume (VWAP/OBV/z-score/relative volume), market structure (breakouts, confirmed swing points, range compression), statistical (skew, kurtosis, autocorrelation, Hurst), and regime (volatility clustering, liquidity proxy), unified behind one canonical `FeatureVector(timestamp, symbol, feature_values, feature_names, metadata, quality_flags, version)` output. Machine-readable manifest at `config/feature_manifest.yaml`. 199 tests. | Tagged `v0.3-feature-engineering`. Not a greenfield build: extends `regime-trader/data/feature_engineering.py`'s existing causal math rather than replacing it (left untouched — no consumer re-pointed yet). Every feature enforces `uses_future_data=False` at registration and passes a registry-driven perturbation test proving causality automatically. Key decisions (canonical `FeatureVector`, registration-time leakage protection, reuse of `market_data.validation` rather than re-cleaning bars, confirmed/lagged swing-point reporting, generated-but-checked-in manifest, deferred cross-symbol correlation + `main.py` wiring): [ADR-003-Feature-Engineering](docs/engineering-handbook/Architecture/ADR/ADR-003-Feature-Engineering.md). Also fixed two real `ta`-library crash bugs (ADX, ATR on short input) and a real pipeline performance bug (row-by-row `.iloc` construction dominating wall time) found via this milestone's own edge-case and performance tests — see the ADR's Verification note. Only exercised against deterministic synthetic bars; not yet run against real historical/live data or wired to any consumer. |
| 4 | HMM & Regime Detection | ✅ Complete | Deterministic, reproducible Gaussian HMM engine (`src/hmm/`): z-score normalization with explicit missing-value handling, Baum-Welch training with configurable state count/covariance type/seed, BIC+AIC model selection, causal forward-algorithm inference (never smoothed/Viterbi), filesystem persistence (`model.pkl`/`normalizer.pkl`/`metadata.json`, versioned per symbol), all behind `RegimeService`, which consumes only `FeatureVector` and produces only the canonical `RegimeState(timestamp, symbol, regime_id, confidence, transition_probability, model_version, feature_pipeline_version, metadata)`. 91 tests (81 unit/integration/quantitative/reproducibility + performance). | Tagged `v0.4-hmm-regime-detection`. Not a greenfield build: ports the causal Forward Algorithm and BIC selection from `regime-trader/core/hmm_engine.py` rather than reimplementing them (left untouched — no consumer re-pointed yet). `RegimeState` frozen ahead of Milestone 5 the same way `FeatureVector` was frozen ahead of this milestone. Key decisions (ported causal algorithms, configurable-not-frozen hyperparameters, explicit missing-value handling, always-compute-both-BIC-and-AIC, filesystem persistence format, hard-fail on feature-version drift at inference — the direct payoff of Milestone 3's `Provenance` work, deferred incremental live inference + `main.py.ModelStore` wiring): [ADR-006-RegimeState-Contract](docs/engineering-handbook/Architecture/ADR/ADR-006-RegimeState-Contract.md) and [ADR-007-HMM-Design](docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md); binding spec: [Standards/RegimeState Contract.md](docs/engineering-handbook/Standards/RegimeState%20Contract.md). Also fixed a real crash bug (`scipy.stats.multivariate_normal.logpdf` raising on a singular covariance matrix from a constant feature) found via this milestone's own constant-series test — see ADR-007's Verification note; the identical unfixed exposure in `regime-trader/core/hmm_engine.py` is flagged as a follow-up, not fixed here. Only exercised against synthetic and real-`FeaturePipeline`-over-synthetic-bars data; not yet run against real historical/live market data or wired to any consumer. Honest performance finding: single inference measured ~20ms over a 252-bar window, not the originally-targeted <5ms — that target assumed the incremental live filter this milestone deliberately deferred; see ADR-007 Decision 7. |
| 5 | Strategy Engine | ✅ Complete | Registry-dispatched regime-tier → allocation logic: `src/strategy/` — `Strategy` protocol (`supports(regime_id)` → `allocate(feature_vector, regime_state)` → `StrategyDecision`), `StrategyRegistry` (`supports()`-only dispatch, no redundant routing map, ambiguous-match detection, opt-in `default_strategy_id` fallback), `StrategyService`, and four reference strategies (growth/bear/mean-reversion/defensive) built on a shared `RegimeMappedStrategy`. Confidence propagates directly from `RegimeState.confidence`; `allocation = base_allocation * confidence`. 83 tests (55 `tests/strategy` + 28 `tests/contracts`, the latter a new cross-package contract-shape regression suite covering `FeatureVector`/`RegimeState`/`StrategyDecision` together). | Tagged `v0.5-strategy-engine`. Closes the `core/regime_strategies.py` half of Known Gaps item 4 (or an earlier phase toward it — see Master Charter's Capability Ownership Map note). First real consumer of the frozen `RegimeState` contract — see [ADR-006](docs/engineering-handbook/Architecture/ADR/ADR-006-RegimeState-Contract.md), [ADR-007](docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md). `StrategyDecision` was frozen ahead of implementation, then implemented — [ADR-008](docs/engineering-handbook/Architecture/ADR/ADR-008-StrategyDecision-Contract.md) (freeze) and [ADR-009](docs/engineering-handbook/Architecture/ADR/ADR-009-Strategy-Engine-Design.md) (design), binding spec: [Standards/StrategyDecision Contract.md](docs/engineering-handbook/Standards/StrategyDecision%20Contract.md). A real fallback-dispatch bug (`allocate()` wrongly re-checking `supports()`, breaking `default_strategy_id`) was found via smoke testing and fixed — see ADR-009 Decision 2. Deliberately out of scope, per the milestone's own charter: no capital/liquidity/leverage checks, no order placement, no broker/risk/memory/NLP integration, no portfolio construction/optimization, no semantic regime labeling (`regime_id` meaning is always caller-supplied — see ADR-009 Decision 4) — those are Milestones 6/7/9/10/11. Measured latency ~0.0096ms/call, comfortably under the <1ms target — see `benchmarks/v0.5-strategy-engine.json`. Not yet wired to any consumer. |
| 6 | Risk Management | ✅ Complete | Converts a `StrategyDecision` (plus a `PortfolioState`/`AccountState` snapshot) into an `ExecutionDecision`: `src/risk/` — small composable validators (one concern each), reduce-only `ExposureCapacitySizing`, portfolio-wide `DrawdownCircuitBreaker`, all behind `RiskService` (`validators → sizing → circuit breakers → ExecutionDecision`). Not order placement. 102 new tests (87 `tests/risk` + 12 `tests/contracts` + 3 closing coverage gaps), 100% line/branch coverage on `src/risk/`. | Tagged `v0.6-risk-management`. A packaged, hardened port of `regime-trader/core/risk_manager.py` (see Capability Ownership Map), grounded in that module's real `VetoDecision`/`CircuitBreakerDecision` shapes and [Standards/Risk Limits Reference.md](docs/engineering-handbook/Standards/Risk%20Limits%20Reference.md)'s actual limits — not a from-scratch build. `ExecutionDecision` was frozen ahead of implementation, then implemented — [ADR-010](docs/engineering-handbook/Architecture/ADR/ADR-010-ExecutionDecision-Contract.md) (freeze) and [ADR-011](docs/engineering-handbook/Architecture/ADR/ADR-011-Risk-Manager-Design.md) (design), binding spec: [Standards/ExecutionDecision Contract.md](docs/engineering-handbook/Standards/ExecutionDecision%20Contract.md). A real redundancy bug (four exposure/leverage validators sharing thresholds with `ExposureCapacitySizing`, making `DecisionType.REDUCED` structurally unreachable) was found via testing and fixed — `RiskService.default()` now favors graceful reduction over hard rejection for exposure/concentration limits; see ADR-011 Decision 1. `approved_allocation` is bounded by `strategy_reference.allocation` (risk only ever reduces size), and a size-cut approval always carries a `risk_adjustments` reason — a deliberate improvement over the legacy `VetoDecision`, which drops that reason today. Deliberately deferred: per-trade dollar risk and correlation filtering (need entry/stop prices and return history no current input provides — see ADR-011 Decision 5), a real liquidity check (`LiquidityValidator` raises `NotImplementedError` per invariant #4 — see ADR-011 Decision 6). Scoped to evaluation only — no broker calls, no order construction (Milestone 7). Measured latency ~0.026ms/call, comfortably under the <1ms target — see `benchmarks/v0.6-risk-management.json`. Not yet wired to any consumer. |
| 7 | Execution Layer | ✅ Complete | Converts an `ExecutionDecision` (plus current `PortfolioState`) into a broker-agnostic `OrderIntent`: `router.py` reconciles target allocation against current position (buy/sell/hold + whole-share quantity), `MarketSnapshotProvider`/`FeatureSnapshotProvider` supply a transient price/ATR observation, a pluggable `StopLossPolicy` (`ATRStopPolicy`/`FixedPercentPolicy`) sizes the stop, and `OrderBuilder`/`ExecutionService` assemble the result. `AlpacaBrokerAdapter` — the only module under `src/execution/` that imports `alpaca-py` — translates `OrderIntent` into a real bracket/OTO order, matching `order_executor.py`'s existing construction logic. `execution.retry.submit_with_retry` gives broker submission genuine idempotent retries via a caller-supplied `idempotency_key`. 85 tests (74 `tests/execution` + 11 `tests/contracts`). | Tagged `v0.7-execution-layer`. A complete reference implementation already existed at `regime-trader/broker/order_executor.py` for order construction/submission — but the price/stop *discovery* problem (`StrategyDecision`/`ExecutionDecision` carry no price data) had no legacy precedent at all, since the old `TradeDecision` arrived with prices pre-computed by the never-built `signal_generator.py`. Resolved by keeping `ExecutionContext`/`FeatureSnapshot` as internal, deliberately *unfrozen* value objects — "execution contracts describe trading intent, not market observations" — rather than widening either frozen upstream contract. `OrderIntent` frozen ahead of implementation — [ADR-012](docs/engineering-handbook/Architecture/ADR/ADR-012-OrderIntent-Contract.md) (contract) and [ADR-013](docs/engineering-handbook/Architecture/ADR/ADR-013-Execution-Layer-Design.md) (design); binding spec: [Standards/OrderIntent Contract.md](docs/engineering-handbook/Standards/OrderIntent%20Contract.md). Deliberately deferred: `LIMIT` orders (contract models them; `AlpacaBrokerAdapter` raises `NotImplementedError`), live bid/ask (no `StreamingDataProvider`-backed `MarketSnapshotProvider` yet), a real per-venue tick-size table, and `VolatilityTierPolicy` (no grounded formula exists anywhere in this codebase to port). Measured latency ~0.017ms/call against fake in-memory providers — excludes real bar-fetch/feature-computation cost; see `benchmarks/v0.7-execution-layer.json`. Not yet wired to any live consumer. Depends on Milestones 5 and 6 (nothing executes without a decision and a veto). |
| 8 | Backtesting & Validation | ✅ Complete | Regime-aware equity backtesting harness, replaying historical bars through the *entire* real decision pipeline (Market Data → Features → HMM → Strategy → Risk → Execution), simulating fills at each bar's own open, and computing performance metrics grouped into returns/risk/exposure/trade-quality. Never retrains models. 123 tests (101 `tests/backtest` + 10 `tests/contracts` + 12 `tests/regression`). | Tagged `v0.8-backtesting`. Partially addresses Known Gaps item 6 — the replay *mechanism* now exists and runs the real pipeline end to end, but item 6 itself specifically requires real historical equity OHLCV and a model trained on it, neither of which this milestone has (synthetic data only, no live credentials); see the updated Known Gaps entry. Built in two explicit phases per the technical lead's instruction: Phase A (`replay.run_replay`) proved deterministic replay to a trade log before any metric was written; Phase B (`metrics/`, `engine.py`) layered performance metrics and `ReplayRun` reproducibility metadata on top. `PortfolioEngine` kept deliberately separate and reusable for future paper trading. A mandatory golden-dataset regression baseline (`tests/regression/`) compares every CI run against a checked-in synthetic scenario within documented tolerance — not exact equality, since this project's own CI matrix's differing numpy/scipy versions make HMM training not bit-identical across it. `BacktestResult` frozen ahead of implementation — [ADR-014](docs/engineering-handbook/Architecture/ADR/ADR-014-BacktestResult-Contract.md) (contract) and [ADR-015](docs/engineering-handbook/Architecture/ADR/ADR-015-Backtesting-Engine-Design.md) (design); binding spec: [Standards/BacktestResult Contract.md](docs/engineering-handbook/Standards/BacktestResult%20Contract.md). Distinct from the existing crypto SMA sandbox in `backtest/`. Only exercised against deterministic synthetic data (`SYNTH`) — no live market-data credentials exist; never mistake it for real historical prices. Measured ~2.8s for a single-symbol, one-year (252-bar) replay; see `benchmarks/v0.8-backtesting.json`. |
| 9 | Adaptive Learning | ✅ Complete | Shadow-mode-only memory loop, built in three explicit phases: Phase A (`InMemoryExperienceStore`/`JsonlExperienceStore`) — an immutable, append-only Experience Store, no learning yet; Phase B (`ThompsonSamplingPolicy`/`BetaArm`, `MemoryService`) — a contextual bandit (Thompson Sampling over Beta posteriors, `(strategy_id, regime_id)` context) producing shadow `LearningDecision`s that never influence `strategy`/`risk`/`execution`; Phase C (`evaluation.evaluate`/`generate_evaluation_report`) — agreement-rate/drift/simulated-P&L/cumulative-regret comparison reporting, read-only. 114 tests (105 `tests/memory` + 9 `tests/contracts`). | Tagged `v0.9-memory-loop`. Adapts, not ports, the legacy `regime-trader/core/learning_engine.py` contextual bandit — same Thompson-Sampling-over-Beta-posteriors update rule, narrower `(strategy_id, regime_id)` context (vs. the legacy `(strategy, regime_label, rsi_bucket)`), a caller-injected `random.Random` for determinism instead of module-level global state. `ExperienceRecord`/`LearningDecision` frozen ahead of implementation — [ADR-016](docs/engineering-handbook/Architecture/ADR/ADR-016-LearningDecision-Contract.md) (contract) and [ADR-017](docs/engineering-handbook/Architecture/ADR/ADR-017-Memory-Loop-Design.md) (design); binding spec: [Standards/LearningDecision Contract.md](docs/engineering-handbook/Standards/LearningDecision%20Contract.md). `recommended_allocation = production_allocation * sampled_weight` — a scaling model that never proposes a larger allocation than production chose, keeping invariant #5 (long-only) intact even in shadow territory. SHAP-based `rationale` and a LightGBM policy are both explicitly deferred in favor of a simple posterior-derived summary and the same bandit the legacy code already validated — see ADR-016/ADR-017's Alternatives Considered. `memory` has zero transitive third-party dependencies, the first package in this handbook with none. Benchmarked insert/update/recommend latency (all sub-millisecond, pure in-memory) — see `benchmarks/v0.9-memory-loop.json`. Letting a `LearningDecision` actually influence production remains a separate, later, explicitly-authorized decision — not what this milestone does. Not yet wired to a real backtest replay or live trading loop as an experience producer. |
| 10 | NLP & Event Processing | ⏳ Planned | FinBERT news sentiment scoring; SHAP trade attribution. | Sentiment reference implementation exists at `regime-trader/core/sentiment_engine.py`. SHAP attribution closes Known Gaps item 5 and is net-new — see [Architecture/SHAP Trade Attribution.md](docs/engineering-handbook/Architecture/SHAP%20Trade%20Attribution.md). Depends on Milestone 5 (needs a real allocation model to attribute). |
| 11 | Signal Orchestration | ⏳ Planned | Final arbitration: merges regime/strategy output (5), adaptive-learning confidence (9), and NLP catalyst signals (10) — gated by risk (6) — into one `TradeDecision`. Conflict resolution, priority rules, conviction scoring. | Closes the `core/signal_generator.py` half of Known Gaps item 4. Deliberately sequenced last among the signal-producing milestones — it has nothing to arbitrate until 5, 9, and 10 all exist. Never bypasses Milestone 6's veto. |
| 12 | Production Monitoring & Deployment | ⏳ Planned | Full production deployment: orchestration, model serving, monitoring, backup/restore, the paper→live gate. | See [Architecture/Production Deployment.md](docs/engineering-handbook/Architecture/Production%20Deployment.md) and [SOPs/Release Workflow.md](docs/engineering-handbook/SOPs/Release%20Workflow.md). Live trading is gated behind this milestone, not before. |

## How this file is maintained

Updated at the close of every milestone — not mid-milestone, and not
speculatively ahead of one starting. On completion:

1. Flip that row's status to ✅, tag the closing commit (`vN-<name>`,
   matching the `v0.1-foundation` convention), and link the tag in the
   Notes column.
2. Update **Last updated** and **Current milestone** above.
3. Cross-check against
   [docs/engineering-handbook/00_MASTER_CHARTER.md](docs/engineering-handbook/00_MASTER_CHARTER.md)'s
   Capability Ownership Map and
   [Architecture/Known Gaps.md](docs/engineering-handbook/Architecture/Known%20Gaps.md) —
   if this milestone closed a tracked gap, move it there too, in the same
   change, per Definition of Done.
4. Add the same milestone to [CHANGELOG.md](CHANGELOG.md), under
   Added/Changed/Known limitations. This file (`PROJECT_STATUS.md`) is the
   forward-looking roadmap and can be freely rewritten as plans change
   (see the 2026-07-12 revision above); `CHANGELOG.md` is the historical
   record of what actually shipped in each tagged version and is never
   rewritten after the fact — the two serve different purposes and neither
   substitutes for the other.

This file summarizes; the handbook is still authoritative on anything it
and this file disagree about.
