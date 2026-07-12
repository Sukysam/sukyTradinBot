# Project Status

Live dashboard of milestone progress for Regime Trader. This file is the
fast answer to "where are we"; for the *why* behind any of it, see
[docs/engineering-handbook/00_MASTER_CHARTER.md](docs/engineering-handbook/00_MASTER_CHARTER.md)
(the constitution this roadmap operates under),
[docs/engineering-handbook/Architecture/Known Gaps.md](docs/engineering-handbook/Architecture/Known%20Gaps.md)
(what's built vs. missing at the component level), and
[docs/Compatibility.md](docs/Compatibility.md) (which contract/package
version each component was built and verified against).

**Last updated**: 2026-07-12 · **Current milestone**: 6 — Risk Management (not yet started)

**Architecture Complete as of `v0.4-hmm-regime-detection`**: not feature
complete, but the core data flow now exists end to end — Market Data →
Feature Pipeline → `FeatureVector` → HMM → `RegimeState` — with every
producer/consumer boundary in that chain a frozen, versioned contract
(`FeatureVector` v2, `RegimeState` v1). Every remaining milestone
(Strategy Engine onward) builds on this pipeline rather than reaching
past it; see [docs/Compatibility.md](docs/Compatibility.md) for the exact
versions.

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
| 6 | Risk Management | ⏳ Planned | Risk veto layer, exposure/concentration limits, circuit breakers, emergency hard stop. | A complete reference implementation already exists at `regime-trader/core/risk_manager.py` (see Capability Ownership Map). This milestone packages/hardens it under `src/`, not a from-scratch build. |
| 7 | Execution Layer | ⏳ Planned | Order construction and submission, broker order lifecycle. | Reference implementation exists at `regime-trader/broker/order_executor.py`. Depends on Milestones 5 and 6 (nothing executes without a decision and a veto). |
| 8 | Backtesting & Validation | ⏳ Planned | Regime-aware equity backtesting harness, replaying the real feature → HMM → strategy path offline. | Closes Known Gaps item 6. Depends on Milestones 2–4 (needs real historical data, the feature pipeline, and a trained model to replay against). Distinct from the existing crypto SMA sandbox in `backtest/`. |
| 9 | Adaptive Learning | ⏳ Planned | Evolve the existing Thompson-sampling contextual-bandit memory loop — or replace it, if a concrete evaluation justifies it — into the system's broader online-learning mechanism. | Reference implementation exists at `regime-trader/core/learning_engine.py`. See [Architecture/Reinforcement Learning Memory Loop.md](docs/engineering-handbook/Architecture/Reinforcement%20Learning%20Memory%20Loop.md). Any replacement decision gets its own ADR before implementation, not assumed here. |
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
