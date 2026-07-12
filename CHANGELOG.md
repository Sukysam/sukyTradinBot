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
