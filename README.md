# Regime Trader

A Hidden Markov Model volatility-regime equity trading platform, plus a
standalone crypto backtesting sandbox. See
[docs/engineering-handbook/00_MASTER_CHARTER.md](docs/engineering-handbook/00_MASTER_CHARTER.md)
for the project's vision, principles, and standards — read it before
making any change to this repository.

**Current status**: see [PROJECT_STATUS.md](PROJECT_STATUS.md) for the
live milestone dashboard and [CHANGELOG.md](CHANGELOG.md) for what's
shipped in each tagged version.

## Repository layout

```
src/common/         foundation package: config, logging, base interfaces, utilities
src/market_data/    market data platform: provider-agnostic models, Alpaca historical +
                     streaming providers, Parquet/DuckDB storage, validation, replay
tests/common/        tests for src/common
tests/market_data/   tests for src/market_data
tests/regime_trader/ contract tests for regime-trader/'s adapter over src/market_data
regime-trader/       the trading platform (HMM regime detection, risk management, execution)
backtest/            standalone crypto strategy research sandbox
docs/                the engineering handbook — read this first
config/              non-secret application configuration (*.example.yaml checked in; real files gitignored)
.github/workflows/   CI
```

Most of `regime-trader/` and all of `backtest/` are pre-existing code
trees not yet brought under this repository's packaging and tooling — the
one exception is `regime-trader/broker/alpaca_client.py`, a Milestone 2
adapter that *is* under full tooling and test coverage. See
[Architecture/Known Gaps.md](docs/engineering-handbook/Architecture/Known%20Gaps.md)
in the handbook for what's built versus planned, and
[Architecture/ADR/](docs/engineering-handbook/Architecture/ADR/) for why.

## Getting started

Requires Python >= 3.9 (CI targets 3.9 and 3.11; see `pyproject.toml`).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,market-data]"

cp .env.example .env   # local environment config; .env is gitignored

pytest                 # run tests
ruff check src tests "regime-trader/broker/alpaca_client.py"   # lint
black --check src tests "regime-trader/broker/alpaca_client.py"  # format check
mypy                   # type check
pre-commit install     # optional: run the same checks automatically on commit
```

## Docker

```bash
docker compose up --build
```

Builds and runs the foundation package's smoke-test entrypoint
(`python -m common`), which loads configuration, configures structured
logging, and emits one log line confirming both work — see the
`Dockerfile`'s header comment for what is and isn't in scope for this
image today.

## Installing market-data / trading-platform dependencies

```bash
pip install -e ".[market-data]"   # src/market_data's own runtime deps (pandas, pyarrow, duckdb, alpaca-py, ...)
pip install -e ".[trading]"       # regime-trader/'s full dependency set (adds scipy, hmmlearn, torch, transformers, ta)
```

Neither installs or runs any trading logic — they only make the
third-party packages the corresponding code imports available in your
environment. See
[ADR-002](docs/engineering-handbook/Architecture/ADR/ADR-002-Market-Data.md)
Decision 4 for why these are two separate extras rather than one.
