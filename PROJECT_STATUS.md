# Project Status

Live dashboard of milestone progress for Regime Trader. This file is the
fast answer to "where are we"; for the *why* behind any of it, see
[docs/engineering-handbook/00_MASTER_CHARTER.md](docs/engineering-handbook/00_MASTER_CHARTER.md)
(the constitution this roadmap operates under) and
[docs/engineering-handbook/Architecture/Known Gaps.md](docs/engineering-handbook/Architecture/Known%20Gaps.md)
(what's built vs. missing at the component level).

**Last updated**: 2026-07-12 · **Current milestone**: 3 — HMM (not started)

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
| 3 | HMM | ⏳ Planned | Regime detection model lifecycle: training, persistence, refresh cadence. | Closes Known Gaps item 3 (model store). A reference forward-inference implementation already exists at `regime-trader/core/hmm_engine.py` — this milestone is expected to build the missing persistence/refresh layer around it, not redo the math. Can now draw on `src/market_data` for historical bars where needed. |
| 4 | Strategies | ⏳ Planned | Adaptive strategy allocation: HMM probabilities + features → trade decisions. | Closes Known Gaps item 4 (`core/signal_generator.py` + `core/regime_strategies.py`). Depends on Milestone 3. |
| 5 | Risk | ⏳ Planned | Risk veto layer, exposure/concentration limits, circuit breakers, emergency hard stop. | A complete reference implementation already exists at `regime-trader/core/risk_manager.py` (see Capability Ownership Map). This milestone packages/hardens it under `src/`, not a from-scratch build. |
| 6 | Execution | ⏳ Planned | Order construction and submission, broker order lifecycle. | Reference implementation exists at `regime-trader/broker/order_executor.py`. Depends on Milestones 2, 4, and 5 (nothing executes without a data source, a decision, and a veto). |
| 7 | Backtesting | ⏳ Planned | Regime-aware equity backtesting harness. | Closes Known Gaps item 6. Depends on Milestones 2 and 3 (needs real historical data and a trained model to replay against). Distinct from the existing crypto SMA sandbox in `backtest/`. |
| 8 | Memory | ⏳ Planned | Reinforcement-learning memory loop, online learning, durable state. | Reference implementation exists at `regime-trader/core/learning_engine.py`. See [Architecture/Reinforcement Learning Memory Loop.md](docs/engineering-handbook/Architecture/Reinforcement%20Learning%20Memory%20Loop.md). |
| 9 | NLP | ⏳ Planned | FinBERT news sentiment scoring; SHAP trade attribution. | Sentiment reference implementation exists at `regime-trader/core/sentiment_engine.py`. SHAP attribution closes Known Gaps item 5 and is net-new — see [Architecture/SHAP Trade Attribution.md](docs/engineering-handbook/Architecture/SHAP%20Trade%20Attribution.md). Depends on Milestone 4. |
| 10 | Production | ⏳ Planned | Full production deployment: orchestration, model serving, monitoring, backup/restore, the paper→live gate. | See [Architecture/Production Deployment.md](docs/engineering-handbook/Architecture/Production%20Deployment.md) and [SOPs/Release Workflow.md](docs/engineering-handbook/SOPs/Release%20Workflow.md). Live trading is gated behind this milestone, not before. |

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

This file summarizes; the handbook is still authoritative on anything it
and this file disagree about.
