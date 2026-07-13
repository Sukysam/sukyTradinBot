# 00 — Master Charter

**Status**: constitutional document. Every standard, workflow, and role
charter in this handbook operates within the principles set out here. If
any other document appears to conflict with this one, this one wins until
the conflict is explicitly resolved and this charter is updated.

This charter, the twelve role charters (`01`–`12`), and the `SOPs/`,
`Prompt Templates/`, `Knowledge Base/`, `Standards/`, and `Architecture/`
folders together form **one canonical documentation system** for this
repository. There is no other documentation tree — an earlier, parallel
`Claude AI Development Kit/` was merged into this handbook and archived;
see this folder's `README.md` for the archive's location if you need
historical context, but treat everything under
`docs/engineering-handbook/` as authoritative and current.

---

## 1. Project Vision

Regime Trader exists to trade a fixed equity watchlist systematically,
using statistically grounded regime detection rather than discretionary
judgment or naive technical rules. The platform's defining bet is that
markets move through detectable volatility/trend regimes, and that
disciplined, risk-gated, continuously-learning execution around that
signal outperforms both static rule-based strategies and undisciplined
manual trading.

Three commitments follow from that bet and shape everything else in this
document:

1. **Statistical rigor over narrative.** A trade is justified by a
   reproducible model output, not a story. Every inference the system
   makes must be traceable to explicit, causal inputs — see the
   anti-look-ahead invariant below.
2. **Capital safety is a harder requirement than returns.** A strategy
   that never blows up beats one with a higher expected return and a fat
   left tail. The risk veto layer exists to enforce this even when every
   other layer of the system is confident.
3. **The system should get better at trading itself over time.** Closed
   trades are not just historical records — they are training signal, fed
   back through a learning loop so the platform's confidence in a given
   setup compounds from real outcomes rather than staying fixed at
   whatever it was calibrated to on day one.

A second, deliberately lower-stakes component, `backtest/`, exists to
validate simple strategy ideas cheaply against crypto data before any
complexity is added to the production platform. It is a sandbox, not a
scaled-down version of the real system — mistakes there cost research
time, not capital, and it is held to a correspondingly lighter standard
throughout this handbook.

The long-term vision is a **production-grade quantitative trading
platform** combining: Hidden Markov Model regime detection, adaptive
strategy allocation, a reinforcement-learning memory loop, online
learning, SHAP-based trade attribution, a FinBERT NLP news engine,
event-driven execution, Alpaca broker integration, a disciplined
backtesting framework, and production-grade deployment — operated with the
rigor of a system that is actually trusted with capital, not a research
prototype that happens to place live orders.

## 2. Capability Ownership Map

The authoritative index of every major capability, its implementation
status, and who owns it (role charters `01`–`12`). Update this table in the
same change that changes a capability's status — it is the single place
anyone should look to answer "is X actually built yet."

| Capability | Status | Primary Owner | Core Module(s) |
|---|---|---|---|
| HMM Regime Detection (live) | **Implemented** | [04 Quant Researcher](04_QUANT_RESEARCHER.md) | `core/hmm_engine.py`, `data/feature_engineering.py` — the still-live production path; not yet re-pointed at `src/hmm/`/`src/features/` |
| Adaptive Strategy Allocation | **Interface defined, logic not yet built** | [07 Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md) | `core/signal_generator.py`, `core/regime_strategies.py` (not yet built) |
| Reinforcement Learning Memory Loop | **Implemented** (contextual multi-armed bandit) | [05 Memory Engineer](05_MEMORY_ENGINEER.md) | `core/learning_engine.py`, `data/trade_context_db.json`, `data/learning_weights.json` |
| Online Learning | **Implemented** (weekly incremental posterior updates) | [05 Memory Engineer](05_MEMORY_ENGINEER.md) / [04 Quant Researcher](04_QUANT_RESEARCHER.md) | `learning_engine.run_weekly_optimization`; HMM refresh cadence is **planned** |
| SHAP Trade Attribution | **Planned** | [04 Quant Researcher](04_QUANT_RESEARCHER.md) (build) / [07 Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md) (integrate) / [11 Documentation Engineer](11_DOCUMENTATION_ENGINEER.md) (audit trail) | `core/attribution.py` (not yet built) |
| FinBERT NLP News Engine | **Implemented** | [06 NLP Engineer](06_NLP_ENGINEER.md) | `core/sentiment_engine.py` |
| Event-Driven Execution | **Implemented** | [01 System Architect](01_SYSTEM_ARCHITECT.md) / [03 Backend Engineer](03_BACKEND_ENGINEER.md) | `main.py` (structural + news pipelines), `broker/news_streamer.py` |
| Market Data Platform | **Implemented** (historical + streaming, Parquet/DuckDB storage, validation, replay) | [03 Backend Engineer](03_BACKEND_ENGINEER.md) | `src/market_data/` — see [ADR-002](Architecture/ADR/ADR-002-Market-Data.md) |
| Alpaca Broker Integration | **Implemented** — order execution and historical data client both built | [03 Backend Engineer](03_BACKEND_ENGINEER.md) | `broker/order_executor.py`; `broker/alpaca_client.py` (adapter over `src/market_data`) |
| Feature Engineering Platform | **Implemented** (39-feature causal registry, `FeaturePipeline`, `FeatureVector`, manifest); `FeatureVector` contract frozen at v2 (with `provenance`); consumed by `src/hmm/`, not yet by anything in `regime-trader/` | [04 Quant Researcher](04_QUANT_RESEARCHER.md) | `src/features/` — see [ADR-003](Architecture/ADR/ADR-003-Feature-Engineering.md), [ADR-004](Architecture/ADR/ADR-004-FeatureVector-Contract-Freeze.md) (contract freeze), and [ADR-005](Architecture/ADR/ADR-005-FeatureVector-Provenance.md) (provenance, v1→v2); binding spec: [Standards/FeatureVector Contract.md](Standards/FeatureVector%20Contract.md). `regime-trader/data/feature_engineering.py` remains the live path until a milestone re-points the live HMM at this pipeline. |
| HMM & Regime Detection Platform | **Implemented** (deterministic Gaussian HMM: normalization, training, BIC/AIC model selection, causal forward-algorithm inference, filesystem persistence, `RegimeService`); `RegimeState` contract frozen at v1; not yet wired to any consumer or to `main.py.ModelStore` | [04 Quant Researcher](04_QUANT_RESEARCHER.md) | `src/hmm/` — see [ADR-006](Architecture/ADR/ADR-006-RegimeState-Contract.md) (contract freeze) and [ADR-007](Architecture/ADR/ADR-007-HMM-Design.md) (design); binding spec: [Standards/RegimeState Contract.md](Standards/RegimeState%20Contract.md). `core/hmm_engine.py` remains the live path — see the "HMM Regime Detection (live)" row above. |
| Strategy Engine (`src/strategy/`) | **Implemented** (registry-dispatched regime→allocation: `StrategyRegistry`, `StrategyService`, four reference strategies — growth/bear/mean-reversion/defensive). Scoped narrower than "Adaptive Strategy Allocation" below (regime-tier only, no sentiment/bandit-confidence inputs, no SHAP, no portfolio construction/optimization, no capital/liquidity/leverage checks, no order placement) — whether Milestone 5 fully closes that capability or is an earlier phase toward it remains a call for whoever builds the next phase, not decided here | [04 Quant Researcher](04_QUANT_RESEARCHER.md) / [07 Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md) | `src/strategy/` — see [ADR-008](Architecture/ADR/ADR-008-StrategyDecision-Contract.md) (contract freeze) and [ADR-009](Architecture/ADR/ADR-009-Strategy-Engine-Design.md) (design); binding spec: [Standards/StrategyDecision Contract.md](Standards/StrategyDecision%20Contract.md). Consumed by `src/risk/` as of Milestone 6; not yet wired to execution, adaptive learning, or signal orchestration. |
| Backtesting Framework | **Implemented** (crypto SMA baseline); **planned** (regime-aware equity backtester) | [04 Quant Researcher](04_QUANT_RESEARCHER.md) | `backtest/` |
| Risk Management & Circuit Breakers | **Implemented** | [08 Risk Manager](08_RISK_MANAGER.md) | `core/risk_manager.py` |
| Risk Management Platform (`src/risk/`) | **Implemented** (validators, reduce-only sizing via `ExposureCapacitySizing`, `DrawdownCircuitBreaker`, `RiskService`); `ExecutionDecision` contract frozen at v1. A packaged, hardened port of `core/risk_manager.py` above, not a from-scratch build — deliberately more permissive by default than the legacy module (graceful reduction over hard rejection for exposure/concentration limits; see ADR-011 Decision 1) | [08 Risk Manager](08_RISK_MANAGER.md) | `src/risk/` — see [ADR-010](Architecture/ADR/ADR-010-ExecutionDecision-Contract.md) (contract freeze) and [ADR-011](Architecture/ADR/ADR-011-Risk-Manager-Design.md) (design); binding spec: [Standards/ExecutionDecision Contract.md](Standards/ExecutionDecision%20Contract.md). Not yet wired to any consumer. Per-trade dollar risk and correlation filtering deliberately not ported (need price/history data no current input provides — see ADR-011 Decision 5). |
| Production Deployment | **Implemented** (process lifecycle); **planned** (orchestration, model serving, drift monitoring) | [12 DevOps Engineer](12_DEVOPS_ENGINEER.md) | `main.py` lifecycle; see [Architecture/Production Deployment.md](Architecture/Production%20Deployment.md) |

Full detail on each row: [Knowledge Base/Capability Architecture Map.md](Knowledge%20Base/Capability%20Architecture%20Map.md).
Full detail on unimplemented rows: [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md).

## 3. Engineering Principles

These are the values every design and code decision is weighed against,
in rough priority order when they conflict:

1. **No look-ahead, ever.** Every feature, every inference, every
   backtest must depend only on information available at the moment a
   decision is made. A look-ahead bug doesn't crash anything — it
   silently flatters backtests and paper-trading results in a way that
   cannot survive contact with live markets. This is the single most
   dangerous class of defect this codebase can contain.
2. **Fail loudly, never silently.** A missing dependency, an unimplemented
   component, an unexpected input — all of these should raise clearly and
   immediately, not degrade gracefully into a plausible-looking but wrong
   result. A system that trades on fabricated logic is worse than a
   system that refuses to trade.
3. **The risk layer is non-negotiable.** No signal, however statistically
   confident, bypasses the risk veto before an order is submitted.
4. **Explicit over implicit.** Interfaces are defined before they're
   implemented against. Thresholds are named constants, not magic
   numbers. Dependencies are injected, not constructed internally.
   Assumptions that must hold (purity, causality, idempotency) are
   asserted or tested, not just believed.
5. **Small, reversible changes over big, risky ones.** Prefer a change
   that can be rolled back cleanly to one that can't. Prefer paper trading
   to live trading until evidence, not confidence, justifies the move.
6. **Documentation explains why, not what.** Code that's readable doesn't
   need comments restating it. It does need to explain non-obvious
   design decisions, workarounds, and constraints.
7. **A human is accountable for every capital-affecting decision.** AI
   assistance accelerates engineering; it does not relocate accountability.

## 4. Non-Negotiable System Invariants

Where the principles above are values to weigh, the invariants below are
hard rules with no exceptions. Each is referenced elsewhere in this
handbook by number (e.g. "invariant #2") — do not renumber this list
without updating every such reference.

1. **No look-ahead, anywhere in the feature/inference/attribution path.**
   Every transform in `data/feature_engineering.py` is strictly causal;
   every live regime read uses `hmm_engine.ForwardFilter`, never
   `predict_proba` (smoothed) or `predict`/`decode` (Viterbi). SHAP
   explanations, once built, must be computed only over features available
   at decision time. See
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
8. **Paper before live.** Nothing in this handbook authorizes flipping
   `ALPACA_PAPER=false` or trading real capital outside of
   [SOPs/Release Workflow.md](SOPs/Release%20Workflow.md)'s explicit gate.
9. **The `FeatureVector` contract is frozen — extend it, never silently
   change it.** Required fields, metadata keys, provenance, feature-
   ordering guarantees, and versioning rules are binding as of
   [ADR-004](Architecture/ADR/ADR-004-FeatureVector-Contract-Freeze.md)
   and [ADR-005](Architecture/ADR/ADR-005-FeatureVector-Provenance.md)
   (currently contract v2); full detail in
   [Standards/FeatureVector Contract.md](Standards/FeatureVector%20Contract.md).
   A breaking change requires a `PIPELINE_VERSION` bump and a new ADR, not
   an in-place redefinition — every consumer (HMM, backtesting, adaptive
   learning, NLP, risk) depends on this contract staying stable.
10. **The `RegimeState` contract is frozen — extend it, never silently
    change it.** Required fields, metadata keys, and versioning rules are
    binding as of
    [ADR-006](Architecture/ADR/ADR-006-RegimeState-Contract.md); full
    detail in
    [Standards/RegimeState Contract.md](Standards/RegimeState%20Contract.md).
    `hmm.service.RegimeService` never exposes `hmmlearn` internals, a raw
    feature matrix, or a normalizer outside the `hmm` package — every
    consumer reads `RegimeState`, never `hmm` internals directly.
11. **The `StrategyDecision` contract is frozen — extend it, never silently
    change it.** Required fields, bounds (`allocation` in `[0.0, 1.0]`,
    `confidence` in `[0.0, 1.0]`, `expected_holding_period` positive,
    `reasoning` non-empty), and versioning rules are binding as of
    [ADR-008](Architecture/ADR/ADR-008-StrategyDecision-Contract.md); full
    detail in
    [Standards/StrategyDecision Contract.md](Standards/StrategyDecision%20Contract.md).
    `strategy.Strategy.allocate` is the only place a `StrategyDecision` is
    constructed — every consumer reads the finished decision, never
    reimplements the allocation formula itself.
12. **The `ExecutionDecision` contract is frozen — extend it, never
    silently change it.** Required fields, bounds (`approved_allocation`
    in `[0.0, strategy_reference.allocation]`, `reasoning` non-empty,
    `risk_adjustments` non-empty whenever the decision is rejected or
    reduced, `decision_type` consistent with the other fields), and
    versioning rules are binding as of
    [ADR-010](Architecture/ADR/ADR-010-ExecutionDecision-Contract.md);
    full detail in
    [Standards/ExecutionDecision Contract.md](Standards/ExecutionDecision%20Contract.md).
    `risk.RiskService.decide` is the only place an `ExecutionDecision` is
    constructed — every consumer reads the finished decision, never
    reimplements the validation/sizing/circuit-breaker logic itself.

## 5. Repository Structure

```
sukyTradinBot/
├── src/common/                    foundation package (Milestone 1): config, structured
│                                   logging, base interfaces, common utilities — no
│                                   trading logic; see the tooling-scope note in
│                                   Architecture/Known Gaps.md
├── src/market_data/               market data platform (Milestone 2): provider-agnostic
│                                   models/interfaces, Alpaca historical + streaming
│                                   providers, Parquet/DuckDB storage, validation, replay
│                                   harness — see Architecture/ADR/ADR-002-Market-Data.md
├── src/features/                  feature engineering platform (Milestone 3): registry-backed
│                                   causal feature library (price/volatility/trend/volume/
│                                   market-structure/statistical/regime), FeaturePipeline,
│                                   canonical FeatureVector output, machine-readable manifest
│                                   at config/feature_manifest.yaml — depends on
│                                   src/market_data for bar cleaning/validation reuse, not the
│                                   reverse; see Architecture/ADR/ADR-003-Feature-Engineering.md
├── src/hmm/                       HMM & regime detection (Milestone 4): deterministic Gaussian
│                                   HMM engine — normalization, training, BIC/AIC model
│                                   selection, causal forward-algorithm inference, filesystem
│                                   persistence, all behind RegimeService — consumes only
│                                   FeatureVector, produces only the canonical RegimeState
│                                   output; depends on src/features (never src/market_data
│                                   directly — this package never touches a raw bar); see
│                                   Architecture/ADR/ADR-007-HMM-Design.md
├── src/strategy/                  strategy engine (Milestone 5): registry-dispatched
│                                   regime -> allocation logic — Strategy Protocol, four
│                                   reference strategies (bull/bear/sideways/defensive),
│                                   StrategyRegistry (supports()-only dispatch, no redundant
│                                   routing map), StrategyService, all behind the canonical
│                                   StrategyDecision output; consumes only FeatureVector +
│                                   RegimeState, no broker/risk/memory/NLP integration; see
│                                   Architecture/ADR/ADR-009-Strategy-Engine-Design.md
├── src/risk/                       risk manager (Milestone 6): converts a StrategyDecision
│                                   (plus PortfolioState/AccountState) into the canonical
│                                   ExecutionDecision — validators (small, composable, one
│                                   concern each), reduce-only sizing (ExposureCapacitySizing),
│                                   a portfolio-wide DrawdownCircuitBreaker, all behind
│                                   RiskService; a packaged, hardened port of
│                                   core/risk_manager.py, not a from-scratch build; consumes
│                                   only strategy.models.StrategyDecision, no broker/memory/NLP
│                                   integration; see Architecture/ADR/ADR-011-Risk-Manager-Design.md
├── tests/common/                  tests for src/common
├── tests/market_data/             tests for src/market_data
├── tests/features/                tests for src/features
├── tests/hmm/                     tests for src/hmm
├── tests/strategy/                tests for src/strategy
├── tests/risk/                     tests for src/risk
├── tests/contracts/                cross-package regression suite verifying FeatureVector/
│                                   RegimeState/StrategyDecision/ExecutionDecision's frozen
│                                   shape, version metadata, serialization round-trips, and
│                                   backward compatibility — distinct from each package's own
│                                   unit tests
├── tests/regime_trader/           contract tests for the regime-trader/ <-> src/market_data
│                                   adapter (see below) — the one exception to "tests/
│                                   mirrors src/", since regime-trader/ isn't a package
│
├── regime-trader/                 the production trading platform
│   ├── main.py                    orchestration: three concurrent pipelines under one asyncio loop
│   ├── core/                      HMM engine, risk manager, sentiment engine, learning engine
│   ├── broker/                    Alpaca order execution, news streaming, and (Milestone 2)
│   │                               alpaca_client.py — a thin adapter over src/market_data,
│   │                               the one file here under this repo's own tooling; see
│   │                               the tooling-scope note in Architecture/Known Gaps.md
│   └── data/                      feature engineering (strictly causal transforms)
│
├── backtest/                      standalone crypto SMA-crossover research sandbox
│                                   (no shared code with regime-trader/; lower stakes)
│
├── docs/
│   └── engineering-handbook/      this handbook — the single canonical documentation system
│       ├── 00_MASTER_CHARTER.md   this file
│       ├── README.md
│       ├── 01–12_*.md             role charters
│       ├── SOPs/                  standard operating procedures
│       ├── Prompt Templates/      reusable prompts for common engineering tasks
│       ├── Knowledge Base/        spec references, glossary, capability maps
│       ├── Standards/             detailed coding/testing/documentation/risk standards
│       ├── Architecture/          system design, data flow, known gaps
│       └── _archive/              superseded documentation, kept for historical reference only
│
├── config/                        non-secret app config (*.example.* checked in; real
│                                   files gitignored) — not config/settings.yaml, the
│                                   still-unbuilt trading config in Known Gaps item 1
├── .github/workflows/             CI (foundation-scoped — see tooling-scope note)
├── pyproject.toml                 packaging, dependency groups, ruff/black/mypy/pytest config
├── Dockerfile, docker-compose.yml foundation-only container image (see Dockerfile header)
├── .pre-commit-config.yaml        local pre-commit hooks (foundation-scoped)
├── .env.example                   documents expected environment variables; real .env is gitignored
│
└── .claude/                       Claude Code session configuration
```

Within `regime-trader/`, the layering is deliberate and enforced in code
review: `main.py` depends on `broker/`, `core/`, and `data/`; `core/`
modules never import from `broker/` or `main.py`; `broker/` never imports
from `core/`. `core/risk_manager.py` importing `data/feature_engineering.py`
for return calculations is the one sanctioned cross-layer import, so the
risk layer's correlation filter and the model's feature matrix never
disagree about what a "return" is. New modules are placed according to
this same discipline — if it's unclear which layer a new file belongs in,
that's a signal to resolve the placement question explicitly before
writing code, not to guess.

As the platform grows, new top-level directories are added deliberately
and documented here in the same change that introduces them — this
section must stay an accurate map of the repository, not a snapshot that
quietly goes stale.

## 6. AI Development Workflow

Significant engineering on this repository is done in collaboration with
AI coding agents (principally Claude Code). This is a deliberate operating
choice, not an incidental detail, and it comes with its own discipline:

1. **Read before writing.** Any AI session doing non-trivial work on this
   repository reads this Master Charter first, and the relevant role
   charter(s) (`01`–`12`) before making changes. Context is loaded
   deliberately and narrowly — the charter(s) relevant to the task at
   hand, not the entire handbook, so sessions stay efficient.
2. **Ground claims in the actual repository state.** An AI session must
   verify a file, function, or dependency exists before relying on it or
   citing it as fact. Memory of a prior session or a prior document is a
   starting hypothesis, not a source of truth.
3. **Distinguish verified fact from reconstruction.** Where this handbook
   states something inferred from code rather than confirmed against an
   authoritative source (e.g. a "Spec Sec. N" citation reconstructed from
   a docstring — see [Knowledge Base/Spec Section Index.md](Knowledge%20Base/Spec%20Section%20Index.md)),
   it says so explicitly.
4. **Match blast radius to autonomy.** Reversible, local changes (editing
   a module, adding a test, drafting documentation) proceed without
   friction. Irreversible or high-blast-radius actions — flipping
   `ALPACA_PAPER` to live, force-pushing, deleting the emergency-halt lock
   file, altering risk thresholds, discarding uncommitted work — always
   require explicit human confirmation in the moment, regardless of any
   standing instruction.
5. **AI-authored code is held to the same bar as human-authored code.**
   No separate, lighter review standard for AI-generated changes. Commits
   and PRs are attributed accurately (AI co-authorship noted, not hidden
   and not overstated).
6. **Escalate uncertainty instead of guessing.** Several structural
   decisions are explicitly unresolved today — see
   [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md) for the
   live list (currently: the model store, `config/settings.yaml`, the
   Adaptive Strategy Allocation model, and SHAP attribution). When a task
   depends on one of these, an AI session states the gap and proposes the
   narrowest interface that unblocks the task, rather than inventing a
   full design unprompted — `main.py` already models this with its
   `Protocol`-based placeholders.
7. **Session hygiene.** Multi-step AI-assisted work is tracked explicitly
   (task lists, todos) so progress and intent are visible to any human
   reviewing the session, and so a resumed or handed-off session can pick
   up context without re-deriving it from scratch.

## 7. Branching Strategy

This repository is not yet under version control (no `.git` directory
exists at the time of writing). The strategy below is the intended
practice from the point `git init` happens — treat initializing version
control as a prerequisite engineering task, since none of the workflow
below (PR-based review, protected branches, CI gating) is enforceable
without it.

- **Trunk-based development.** `main` is always in a deployable (paper-
  trading-ready) state. No direct commits to `main` — all changes land via
  pull request.
- **Short-lived feature branches**, named
  `<type>/<short-description>`, where `<type>` is one of `feat`, `fix`,
  `refactor`, `docs`, `test`, or `chore` — e.g. `feat/alpaca-historical-client`,
  `fix/correlation-filter-nan-handling`. Branches live days, not weeks; if a
  branch is growing stale, split it rather than letting it drift from
  `main`.
- **No long-lived parallel branches** for major features. Prefer landing
  incomplete-but-inert work behind an explicit `NotImplementedError`
  placeholder (invariant #4) over maintaining a divergent branch — this
  keeps integration continuous and matches how this codebase already
  handles unbuilt dependencies.
- **`main` is protected**: no force-push, no history rewriting, requires
  passing CI and at least one review approval before merge (see Review
  Process).
- **Releases** are tagged, not branched, unless a live-trading deployment
  genuinely needs to diverge from `main` temporarily — see
  [SOPs/Release Workflow.md](SOPs/Release%20Workflow.md) for the
  paper→live gate that governs this in practice.
- **Commit messages** state why a change was made, not just what changed.

## 8. Definition of Done

A change is not done until all of the following hold. This is the minimum
bar; individual role charters add capability-specific criteria on top of
it, never relax it.

1. **Correctness**: the change does what it claims, verified by tests at
   the appropriate tier (see Testing Standards) — not just "it ran once
   without an exception."
2. **No invariant violations**: none of the twelve invariants in Section 4
   are violated.
3. **Reviewed**: passed the Review Process below, with every blocking or
   needs-discussion finding resolved, not just acknowledged.
4. **Tested**: new or changed pure-function logic has unit tests covering
   its documented edge cases; new integration points have integration
   tests or an explicit, reasoned exception noted in the PR.
5. **Documented**: any new module has a docstring explaining its purpose
   and at least one non-obvious design decision, if it has one. Any change
   to a capability's status (Section 2), a threshold, an architectural
   boundary, or a spec-cited behavior is reflected in this handbook in the
   same change — not deferred to a follow-up.
6. **Scoped**: the change does what it says and nothing else — no
   unrelated refactors, no speculative abstraction for hypothetical future
   needs, no scope creep absorbed silently into an unrelated PR.
7. **Safe by default**: any new configuration defaults to the safer
   option (paper over live, conservative over aggressive, fail-closed over
   fail-open) unless explicitly and deliberately overridden.

A PR that satisfies 1–4 but skips 5 or 6 is not done — it's done later,
which in practice often means never.

## 9. Documentation Standards

- **Docstrings explain why.** Every module docstring states its purpose
  and, where relevant, cites the spec section it implements (see
  [Knowledge Base/Spec Section Index.md](Knowledge%20Base/Spec%20Section%20Index.md))
  and explains any non-obvious design decision. A docstring that only
  restates the class/function names below it is not pulling its weight.
- **Significant, hard-to-reverse decisions get an Architecture Decision
  Record.** See [Architecture/ADR/README.md](Architecture/ADR/README.md)
  for when one is warranted and the format to use. A docstring explains
  why a module is shaped the way it is; an ADR explains why the codebase
  as a whole made a foundational choice — the two operate at different
  altitudes and neither substitutes for the other.
- **This handbook is versioned with the code it describes.** Documentation
  changes ship in the same PR as the code change that motivates them.
- **Distinguish verified from reconstructed.** Any claim about an external
  spec, requirement, or stakeholder decision that isn't backed by a
  locatable source document is marked as reconstructed/inferred.
- **Markdown conventions**: relative links between handbook documents;
  tables for structured comparisons (thresholds, capability status,
  ownership); code blocks for anything meant to be copy-pasted or matched
  exactly.
- **No orphaned documentation.** A document that no longer reflects
  reality is corrected or removed promptly. Stale documentation is a bug.
- **Cross-references over duplication.** When two documents would
  otherwise repeat the same content, one is authoritative and the other
  links to it.
- **One canonical structure.** Documentation for this project lives only
  under `docs/engineering-handbook/`. Do not create a second, parallel
  documentation tree — extend this one.

## 10. Coding Standards

- **Language conventions**: `from __future__ import annotations`; type
  hints on all public functions; `@dataclass(frozen=True)` for value
  objects with no mutation need; `Enum` for closed sets of named outcomes;
  `typing.Protocol` for a dependency with more than one implementation, or
  one that doesn't exist yet and needs a stable contract to build against.
- **Pure functions by default.** Reach for a class only when there is
  genuine state to hold across calls. Financial-logic modules in
  particular (risk checks, feature transforms) are held to a strict
  "pure function of explicit inputs" discipline.
- **Dependency injection over hidden construction.** Any component with an
  external dependency (a broker client, a fitted model, a file path)
  receives it as a constructor/function parameter.
- **Named constants, not magic numbers.** Every tunable threshold or
  configuration value is a module-level `UPPER_SNAKE_CASE` constant.
- **Specific exceptions, loud failures.** Catch specific exception types;
  reserve broad exception handling for the few places that must contain a
  failure to protect a long-running loop.
- **Reproducibility.** Any source of randomness (model fitting, sampling)
  takes an explicit, logged seed.
- **Security**: no credential, API key, or secret is ever committed,
  logged, or included in an exception message.

Detailed, example-driven versions of these standards, plus process-level
standards not covered here, live in:
[Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md),
[Standards/Coding Standards.md](Standards/Coding%20Standards.md),
[Standards/Anti-Lookahead Checklist.md](Standards/Anti-Lookahead%20Checklist.md),
[Standards/Risk Limits Reference.md](Standards/Risk%20Limits%20Reference.md),
[Standards/Model Explainability Standard.md](Standards/Model%20Explainability%20Standard.md), and
[Standards/Communication Protocols.md](Standards/Communication%20Protocols.md).
This section is the binding summary; those documents are the binding detail.

## 11. Testing Standards

Testing priority is set by blast radius, not by what's easiest to test
first:

1. **Risk and safety logic** (the risk veto layer, circuit breakers) —
   highest priority. Pure and stateless by design, so full boundary
   coverage (just under / at / just over every threshold) is achievable
   and non-negotiable.
2. **Anti-look-ahead correctness** (feature transforms, regime inference)
   — every feature column needs a regression test proving a future value
   cannot influence an earlier computed value; live inference paths need
   tests proving they never consult smoothed or future-aware model output.
3. **Order construction and broker interaction** — mocked against the
   broker client, never exercised against a live or paper API in the fast
   suite.
4. **Learning-loop correctness** — idempotency of any batched/periodic
   update process is a hard requirement, verified directly, not assumed.
5. **External-model-dependent logic** (NLP sentiment scoring and similar)
   — covered by a slower, clearly separated integration tier.

General standards:

- Tests state the behavior under test and the expected outcome in their
  name, not just the function being exercised.
- Any test touching a filesystem path uses a temp-directory override.
- Time-sensitive logic is tested by injecting an explicit timestamp
  parameter, never by sleeping through real intervals.
- A backtest result is not accepted as evidence of anything without a
  stated out-of-sample methodology and transaction-cost assumptions.
- CI separates fast (no external model download, no network) tests from
  slow integration tests.

The full module-by-module priority list and rationale lives in
[09_QA_ENGINEER.md](09_QA_ENGINEER.md).

## 12. Review Process

- **Every change is reviewed before merge.** No exceptions for "small"
  changes to `regime-trader/`; `backtest/` and pure-documentation changes
  may use a lighter-touch review given their lower stakes.
- **Severity language**, used consistently in review comments, PR
  descriptions, and escalations — full definitions in
  [Standards/Communication Protocols.md](Standards/Communication%20Protocols.md):
  - **Blocking** — violates an invariant (Section 4) or principle
    (Section 3). Do not merge until resolved.
  - **Needs discussion** — a design or threshold question requiring
    explicit sign-off from the owning role charter before merging.
  - **Non-blocking** — style, naming, or minor improvement suggestions
    that don't gate the merge.
- **Reviewers check, in order**: correctness against stated intent,
  invariant compliance (Section 4), test adequacy (Section 11),
  documentation currency (Section 9), and scope discipline (Section 8).
- **A finding that reveals a pre-existing issue elsewhere in the
  codebase** — not just in the diff under review — is filed as its own
  follow-up, not silently folded into the current PR's scope.
- **The author self-checks against this charter and the relevant
  standards before requesting review.**
- Detailed, capability-specific review checklists live in
  [10_CODE_REVIEWER.md](10_CODE_REVIEWER.md).

## 13. Roles Overview

Twelve role charters, each owning a distinct seam of the system. Each
defines: what it owns, what it can decide unilaterally, what it must
escalate, its acceptance criteria, its coding standards, and its
communication protocol — all operating within this Master Charter. Load
the one or two role files relevant to the task at hand; you rarely need
all twelve in context simultaneously.

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
| 10 | [Code Reviewer](10_CODE_REVIEWER.md) | Review checklist tied to the invariants in Section 4 |
| 11 | [Documentation Engineer](11_DOCUMENTATION_ENGINEER.md) | Docstrings, spec cross-references, model cards, attribution audit trail, this handbook |
| 12 | [DevOps Engineer](12_DEVOPS_ENGINEER.md) | Secrets, process supervision, production deployment, monitoring |

No role has authority to override this Master Charter unilaterally. Where
a role's charter and this document conflict, this document governs until
the conflict is resolved and this charter is explicitly amended.

---

*This charter is a living document. Amend it deliberately, in its own
reviewed change, when the project's vision, principles, or standards
genuinely change — not incidentally as a side effect of unrelated work.*
