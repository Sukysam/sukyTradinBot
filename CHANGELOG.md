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
