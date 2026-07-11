# 00 — Master Charter

## Purpose of this Kit

This Kit is the operating system for every Claude session — interactive or
agentic — that works on this repository. It exists so that:

- Any session, cold-started with zero prior context, reaches the same
  mental model of the system that a senior engineer on this project would
  have.
- Role-specific judgment calls (what a Risk Manager is allowed to change
  unilaterally, what a Quant Researcher must never do to the inference
  path) don't have to be re-explained in every prompt.
- The gap between "what this system is designed to be" and "what is
  actually implemented today" is tracked explicitly, not papered over.

Load this file first in any Claude Project built on this repository. Load
the one or two role files relevant to the task at hand from the table
below — you rarely need all thirteen in context simultaneously.

## What this system is

**Regime Trader** is a production-grade quantitative trading platform that
trades a fixed equity watchlist through Alpaca. Its design combines:

- **Hidden Markov Model regime detection** — a Gaussian HMM fitted per
  ticker, run through a strictly causal forward filter, to classify the
  market into volatility/trend regimes in real time.
- **Adaptive strategy allocation** — regime state, technical features, and
  sentiment combine to decide what to trade and how much to allocate,
  re-weighted continuously by the learning loop below.
- **A Reinforcement Learning memory loop** — closed trades are stored as
  contextual experience and fed back through a Thompson Sampling contextual
  bandit, so the system's confidence in a given (strategy, regime,
  technical-context) setup compounds over time from real outcomes.
- **Online learning** — the bandit's posteriors update incrementally on a
  weekly cadence from newly closed trades, without a full retrain, so the
  system adapts within a live deployment rather than only at redeploy time.
- **SHAP trade attribution** — every automated trade decision is designed
  to carry a feature-level explanation of *why* the model proposed it, for
  audit, debugging, and regulatory defensibility.
- **A FinBERT NLP news engine** — headline sentiment scored in real time,
  capable of independently triggering a catalyst trade off breaking news.
- **Event-driven execution** — trading decisions are produced by two
  independent triggers (a 5-minute structural cadence and a news
  WebSocket), not a single polling loop.
- **Alpaca broker integration** — order construction, bracket/OCO
  submission, and position lifecycle management against Alpaca's paper and
  live trading APIs.
- **A backtesting framework** — historical validation with an
  out-of-sample discipline, independent of the live trading code path.
- **Production deployment** — a supervised, monitored, restart-safe
  process with a human-gated emergency stop.

A second, unrelated component, `backtest/`, is a standalone SMA-crossover
grid-search backtester against Binance public klines (crypto). It shares no
code with the equity platform and exists to sanity-check simple strategies
cheaply. Treat it as a lower-stakes sandbox — mistakes there cost research
time, not capital.

## Capability Ownership Map

The authoritative index of every major capability, its implementation
status, and who owns it. Update this table the same PR that changes a
capability's status — it is the single place anyone should look to answer
"is X actually built yet."

| Capability | Status | Primary Owner | Core Module(s) |
|---|---|---|---|
| HMM Regime Detection | **Implemented** | [Quant Researcher](04_QUANT_RESEARCHER.md) | `core/hmm_engine.py`, `data/feature_engineering.py` |
| Adaptive Strategy Allocation | **Interface defined, logic not yet built** | [Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md) | `core/signal_generator.py`, `core/regime_strategies.py` (not yet built) |
| Reinforcement Learning Memory Loop | **Implemented** (contextual multi-armed bandit) | [Memory Engineer](05_MEMORY_ENGINEER.md) | `core/learning_engine.py`, `data/trade_context_db.json`, `data/learning_weights.json` |
| Online Learning | **Implemented** (weekly incremental posterior updates) | [Memory Engineer](05_MEMORY_ENGINEER.md) / [Quant Researcher](04_QUANT_RESEARCHER.md) | `learning_engine.run_weekly_optimization`; HMM refresh cadence is **planned** |
| SHAP Trade Attribution | **Planned** | [Quant Researcher](04_QUANT_RESEARCHER.md) (build) / [Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md) (integrate) / [Documentation Engineer](11_DOCUMENTATION_ENGINEER.md) (audit trail) | `core/attribution.py` (not yet built) |
| FinBERT NLP News Engine | **Implemented** | [NLP Engineer](06_NLP_ENGINEER.md) | `core/sentiment_engine.py` |
| Event-Driven Execution | **Implemented** | [System Architect](01_SYSTEM_ARCHITECT.md) / [Backend Engineer](03_BACKEND_ENGINEER.md) | `main.py` (structural + news pipelines), `broker/news_streamer.py` |
| Alpaca Broker Integration | **Partial** — order execution implemented; historical data client not yet built | [Backend Engineer](03_BACKEND_ENGINEER.md) | `broker/order_executor.py`; `broker/alpaca_client.py` (not yet built) |
| Backtesting Framework | **Implemented** (crypto SMA baseline); **planned** (regime-aware equity backtester) | [Quant Researcher](04_QUANT_RESEARCHER.md) | `backtest/` |
| Risk Management & Circuit Breakers | **Implemented** | [Risk Manager](08_RISK_MANAGER.md) | `core/risk_manager.py` |
| Production Deployment | **Implemented** (process lifecycle); **planned** (orchestration, model serving, drift monitoring) | [DevOps Engineer](12_DEVOPS_ENGINEER.md) | `main.py` lifecycle; deployment tooling in `Architecture/Production Deployment.md` |

Full detail on each row: [Knowledge Base/Capability Architecture Map.md](Knowledge%20Base/Capability%20Architecture%20Map.md).
Full detail on unimplemented rows: [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md).

## The spec

Source code docstrings throughout `regime-trader/` cite **"Spec Sec. N"**
(e.g. "Spec Sec. 5" for risk limits). That spec is ground truth for
*intended* behavior; this Kit describes how to work *within* that intent.
See [Knowledge Base/Spec Section Index.md](Knowledge%20Base/Spec%20Section%20Index.md)
for the section → module map reconstructed from those citations. If the
authoritative spec document surfaces, reconcile that index against it.

## Non-negotiable invariants

These hold regardless of which role file is in context. Each was written
into the code (or into this Kit's target architecture) deliberately — do
not casually refactor past them:

1. **No look-ahead, anywhere in the feature/inference/attribution path.**
   Every transform in `data/feature_engineering.py` is strictly causal;
   every live regime read uses `hmm_engine.ForwardFilter`, never
   `predict_proba` (smoothed) or `predict`/`decode` (Viterbi). SHAP
   explanations, once built, must be computed only over features available
   at decision time — an attribution that references a future bar is a
   correctness bug, not just an interpretability one. See
   [Standards/Anti-Lookahead Checklist.md](Standards/Anti-Lookahead%20Checklist.md).
2. **The risk veto is the only gate on order submission.** No code path may
   call `OrderExecutor.submit_entry_order` without first passing the trade
   through `risk_manager.evaluate_trade`.
3. **The emergency halt lock file is human-cleared only.** Never write code
   that deletes or bypasses `risk_manager.EMERGENCY_HALT.lock`
   programmatically.
4. **Missing components fail loudly, not silently.** Where a dependency
   doesn't exist yet (see [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md)),
   wire in a placeholder that raises `NotImplementedError` on first use
   (`main.py`'s `_NotYetImplemented` pattern) rather than a stub that
   quietly no-ops or fabricates a plausible-looking result.
5. **Every strategy is long-only.** `OrderExecutor` only ever issues `BUY`
   entries with an attached stop. Don't add short-side code without an
   explicit spec citation authorizing it.
6. **Every automated trade decision must be explainable and logged before
   it is actionable in production.** Once SHAP attribution is built, no
   trade decision ships to `risk_manager.evaluate_trade` without an
   attached attribution record. Until then, `TradeDecision`'s rationale
   fields (`strategy`, `regime_label`, `rsi_14`) are the minimum acceptable
   substitute — never submit an order with no reconstructable rationale.
7. **Online learning updates are additive and reversible, never destructive.**
   `LearningEngine`'s posteriors accumulate; nothing in this system may
   overwrite `learning_weights.json` wholesale outside of an explicit,
   reviewed reset procedure. Same principle applies to any future online
   model-weight update mechanism.
8. **Paper before live.** Nothing in this Kit authorizes flipping
   `ALPACA_PAPER=false` or trading real capital. See
   [SOPs/Release Workflow.md](SOPs/Release%20Workflow.md).

## How the role files work

Each `NN_ROLE.md` file is a complete operating charter for one hat: mandate,
capability ownership, core workflows, acceptance criteria, coding
standards, communication protocols, decision rights, and pitfalls specific
to that seam of the codebase.

| # | Role | Owns |
|---|------|------|
| 01 | [System Architect](01_SYSTEM_ARCHITECT.md) | Module boundaries, `Protocol` interfaces, async orchestration, event-driven execution shape |
| 02 | [Technical Planner](02_TECHNICAL_PLANNER.md) | Breaking spec sections and capabilities into buildable increments, gap tracking |
| 03 | [Backend Engineer](03_BACKEND_ENGINEER.md) | `broker/`, `main.py` plumbing, Alpaca integration |
| 04 | [Quant Researcher](04_QUANT_RESEARCHER.md) | HMM regime detection, feature engineering, backtesting framework, SHAP model build |
| 05 | [Memory Engineer](05_MEMORY_ENGINEER.md) | RL memory loop, online learning persistence, durable state, model store |
| 06 | [NLP Engineer](06_NLP_ENGINEER.md) | FinBERT sentiment engine |
| 07 | [Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md) | Adaptive strategy allocation, trade decision synthesis, SHAP integration |
| 08 | [Risk Manager](08_RISK_MANAGER.md) | Risk veto layer, circuit breakers, exposure limits |
| 09 | [QA Engineer](09_QA_ENGINEER.md) | Test strategy, backtest validation, model/drift validation, paper-trading gates |
| 10 | [Code Reviewer](10_CODE_REVIEWER.md) | Review checklist tied to the invariants above |
| 11 | [Documentation Engineer](11_DOCUMENTATION_ENGINEER.md) | Docstrings, spec cross-references, model cards, attribution audit trail, this Kit |
| 12 | [DevOps Engineer](12_DEVOPS_ENGINEER.md) | Secrets, process supervision, production deployment, monitoring |

## Shared standards referenced by every role

- [Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md)
- [Standards/Coding Standards.md](Standards/Coding%20Standards.md)
- [Standards/Communication Protocols.md](Standards/Communication%20Protocols.md)
- [Standards/Anti-Lookahead Checklist.md](Standards/Anti-Lookahead%20Checklist.md)
- [Standards/Risk Limits Reference.md](Standards/Risk%20Limits%20Reference.md)
- [Standards/Model Explainability Standard.md](Standards/Model%20Explainability%20Standard.md)

## Escalate, don't assume

Several structural decisions are explicitly unresolved today (see
[Architecture/Known Gaps.md](Architecture/Known%20Gaps.md)) — where a
fitted HMM model per ticker is persisted and refreshed, what
`config/settings.yaml` should contain, what model backs adaptive
allocation, and how SHAP attribution attaches to a `TradeDecision`. When a
task depends on one of these, say so and propose the narrowest interface
that unblocks the task, rather than inventing a full design unprompted.
`main.py` already models this posture: it defines `Protocol` interfaces for
missing pieces instead of guessing at their implementation.

## Communication protocol at the Kit level

- Every PR states which role(s) it operates under, using the table above.
- Every escalation (see each role file's "Must Escalate" section) is
  raised explicitly in the PR description or task thread, addressed to the
  owning role by name — not left implicit for a reviewer to infer.
- Status updates on multi-step work follow
  [Standards/Communication Protocols.md](Standards/Communication%20Protocols.md)'s
  cadence and format.
