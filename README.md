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

The full decision pipeline, in the order data flows through it:

```
src/common/         foundation package: config, logging, base interfaces, utilities
src/market_data/    provider-agnostic models, Alpaca historical + streaming providers,
                     Parquet/DuckDB storage, validation, replay
src/features/       causal feature pipeline -> FeatureVector (v2, frozen)
src/hmm/            Gaussian HMM regime detection -> RegimeState (v1, frozen)
src/strategy/       regime-tier allocation logic -> StrategyDecision (v1, frozen)
src/risk/           validators/sizing/circuit breakers -> ExecutionDecision (v1, frozen)
src/execution/      order construction + broker adapter -> OrderIntent (v1, frozen)
src/backtest/       regime-aware equity backtesting harness -> BacktestResult (v1, frozen)
src/memory/         adaptive learning (shadow mode) -> LearningDecision (v1, frozen)
src/nlp/            news sentiment engine (shadow mode) -> NewsSignal (v1, frozen)
src/orchestration/  reconciles Strategy/Memory/NLP signals -> FinalDecision (v1, frozen)
src/ops/            operational maturity: health, observability, config/secrets,
                     deployment/release, diagnostics — see docs/operations/
tests/               one directory per src/ package, plus tests/contracts/ (cross-package
                     contract-shape regression) and tests/regression/ (golden-dataset backtest)
regime-trader/      the pre-existing trading platform this repo is incrementally replacing
backtest/            standalone crypto strategy research sandbox (distinct from src/backtest/)
docs/                the engineering handbook (read this first) + docs/operations/ runbooks
config/              non-secret application configuration (*.example.yaml checked in; real files gitignored)
benchmarks/          per-milestone latency/throughput measurements (JSON)
.github/workflows/   CI
```

Each `src/` package's frozen output contract, version, and consumers
are tracked in [docs/Compatibility.md](docs/Compatibility.md) — check
it before changing anything a contract's shape depends on.
`regime-trader/` and the top-level `backtest/` sandbox are pre-existing
code trees, most of which are not yet brought under this repository's
packaging and tooling; the one exception is
`regime-trader/broker/alpaca_client.py`, a Milestone 2 adapter under
full tooling and test coverage. See
[Architecture/Known Gaps.md](docs/engineering-handbook/Architecture/Known%20Gaps.md)
in the handbook for what's built versus planned, and
[Architecture/ADR/](docs/engineering-handbook/Architecture/ADR/) (26
ADRs as of Milestone 12) for why.

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
