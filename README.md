# Regime Trader

A Hidden Markov Model volatility-regime equity trading platform, plus a
standalone crypto backtesting sandbox. See
[docs/engineering-handbook/00_MASTER_CHARTER.md](docs/engineering-handbook/00_MASTER_CHARTER.md)
for the project's vision, principles, and standards — read it before
making any change to this repository.

## Repository layout

```
src/common/        foundation package: config, logging, base interfaces, utilities
tests/              tests for src/common
regime-trader/      the trading platform (HMM regime detection, risk management, execution)
backtest/           standalone crypto strategy research sandbox
docs/               the engineering handbook — read this first
config/             non-secret application configuration (*.example.yaml checked in; real files gitignored)
.github/workflows/  CI
```

`regime-trader/` and `backtest/` are pre-existing code trees not yet
brought under this repository's packaging and tooling — see
[Architecture/Known Gaps.md](docs/engineering-handbook/Architecture/Known%20Gaps.md)
in the handbook for what's built versus planned.

## Getting started

Requires Python >= 3.9 (CI targets 3.9 and 3.11; see `pyproject.toml`).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # local environment config; .env is gitignored

pytest                 # run tests
ruff check src tests   # lint
black --check src tests  # format check
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

## Installing trading-platform dependencies

`regime-trader/` and `backtest/` are not yet packaged, but their runtime
dependencies are declared for reference and installability:

```bash
pip install -e ".[trading]"
```

This does not install or run any trading logic — it only makes the
third-party packages `regime-trader/`'s existing modules import available
in your environment.
