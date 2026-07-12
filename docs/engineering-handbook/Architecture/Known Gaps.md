# Architecture — Known Gaps

Live-updated list of components this system's design depends on that don't
exist yet. Sourced from `main.py`'s own module docstring and its
`_NotYetImplemented` wiring, extended to cover the capabilities named in
the Master Charter's Capability Ownership Map that are still Planned. The
code is deliberately honest about missing pieces rather than papering over
them with a stub that fails silently — this document extends that honesty
to the handbook level.

**Update this file in the same PR that closes a gap.** Per
[11_DOCUMENTATION_ENGINEER.md](../11_DOCUMENTATION_ENGINEER.md), don't
defer it to a follow-up. Item numbers below match
[02_TECHNICAL_PLANNER.md](../02_TECHNICAL_PLANNER.md)'s build order — keep
the two in sync if either changes.

## Open gaps (as of 2026-07-12)

### 1. `config/settings.yaml`
Doesn't exist. `main.py` currently falls back to the
`REGIME_TRADER_TICKERS` env var for the ticker list and hardcodes
`sectors={}`, which silently no-ops the risk manager's sector-exposure cap
(`check_exposure_limits`'s sector check can never trigger with an empty
sector map). Acceptable in paper trading; **blocking for live** per
[SOPs/Release Workflow.md](../SOPs/Release%20Workflow.md). Owner:
[02_TECHNICAL_PLANNER.md](../02_TECHNICAL_PLANNER.md) / [System Architect](../01_SYSTEM_ARCHITECT.md).

### 3. A trained-HMM-model store (partially closed by Milestone 4)
Was: satisfies `main.py.ModelStore`: `get_model(ticker) -> GaussianHMM`.
Persistence itself is now real — `hmm.persistence.save`/`load` writes/reads
a versioned, per-symbol artifact (`model.pkl`, `normalizer.pkl`,
`metadata.json`) via `hmm.service.RegimeService.save`/`load`; see
[ADR-007](ADR/ADR-007-HMM-Design.md) Decision 5. What remains open:
`main.py.ModelStore.get_model(ticker)` still returns a raw `GaussianHMM`,
which `RegimeService` deliberately never exposes (see ADR-007's "never
expose hmmlearn internals" requirement) — reconciling the two Protocols is
explicitly deferred to whichever milestone first wires a real consumer to
`src/hmm/` (see ADR-007 Decision 7). Refresh cadence (when a persisted
model gets retrained) is still undecided — this is also the blocker for
"online learning" of the HMM layer itself (today, online learning is
implemented only for the RL memory loop's bandit — see
[Architecture/Reinforcement Learning Memory Loop.md](Reinforcement%20Learning%20Memory%20Loop.md)).
Owner: [05_MEMORY_ENGINEER.md](../05_MEMORY_ENGINEER.md) (refresh cadence),
[04_QUANT_RESEARCHER.md](../04_QUANT_RESEARCHER.md) (`src/hmm/` itself).

### 4. `core/signal_generator.py` + `core/regime_strategies.py` (Adaptive Strategy Allocation)
Satisfies `main.py.SignalGenerator`: `evaluate_bar(...)` and
`evaluate_catalyst(...)`, both returning `Optional[TradeDecision]`. Owns
the HMM-probabilities → regime tier → allocation logic (Spec Sec. 3), the
`trade_context_db.json` entry-snapshot write (Spec Sec. 4), and hosts the
Adaptive Strategy Allocation model per
[04_QUANT_RESEARCHER.md](../04_QUANT_RESEARCHER.md)'s target architecture.
The single largest remaining piece of business logic in the system.
Depends on item 3. Owner: [07_SIGNAL_ORCHESTRATOR.md](../07_SIGNAL_ORCHESTRATOR.md).

### 5. `core/attribution.py` (SHAP Trade Attribution)
Per-trade feature attribution for the Adaptive Strategy Allocation model.
See [Architecture/SHAP Trade Attribution.md](SHAP%20Trade%20Attribution.md)
for the full target architecture and
[Standards/Model Explainability Standard.md](../Standards/Model%20Explainability%20Standard.md)
for binding requirements. Depends on item 4 — there is nothing to
attribute until a real decision-making model exists; do not begin this
before item 4 has a working, backtested implementation. Owner:
[04_QUANT_RESEARCHER.md](../04_QUANT_RESEARCHER.md) (build),
[07_SIGNAL_ORCHESTRATOR.md](../07_SIGNAL_ORCHESTRATOR.md) (integrate).

### 6. Regime-aware equity backtesting harness
Today's `backtest/` only validates simple crypto SMA-crossover logic and
cannot validate anything HMM- or regime-specific. A regime-aware harness
needs real historical equity OHLCV (item 2) and a trained model per ticker
(item 3) to replay the structural loop's decision path offline. Depends on
items 2 and 3. Owner: [04_QUANT_RESEARCHER.md](../04_QUANT_RESEARCHER.md).

## How a gap is wired today

Items 1, 3, and 4 above are (or, for item 4, will be) injected into
`RegimeTraderApp` in `main.py`'s `main()` function as
`_NotYetImplemented(missing_component_description)` instances, whose
`__getattr__` raises `NotImplementedError` the moment the structural loop
actually calls a method on it — item 2 was wired this way until Milestone
2 replaced its placeholder with a real implementation (see Resolved gaps
below). This means:

- Running `main()` today starts cleanly and fails loudly and specifically
  the first time the structural loop needs one of these, rather than
  silently no-op'ing or fabricating a decision.
- A `NotImplementedError` in production logs citing one of these
  components is *expected* until it's built — see
  [SOPs/Bug Fix Workflow.md](../SOPs/Bug%20Fix%20Workflow.md) step 3 before
  treating it as a bug.

Items 5 and 6 are not `Protocol`-wired dependencies of `main.py` — they are
downstream capabilities that simply don't exist as modules yet. Their
"not implemented" state is tracked here, not via a runtime placeholder.

## Tooling scope (Milestone 1: Foundation; updated Milestone 2, Milestone 3, Milestone 4)

Milestone 1 added real packaging and tooling — `pyproject.toml`, Ruff,
Black, MyPy, Pytest, pre-commit, GitHub Actions CI, and a Docker/Compose
setup — but scoped all of it to the new `src/common/` foundation package
and `tests/`, deliberately excluding `regime-trader/` and `backtest/`.
This is a gap, not an oversight, and is tracked here so it doesn't quietly
become permanent:

- **Why excluded**: Milestone 1's explicit brief was "no trading logic" —
  reformatting or lint-fixing `regime-trader/`'s existing files, even
  mechanically, was treated as touching trading code and out of scope.
  Running strict tooling against code that predates it and can't be
  brought into compliance in the same change would also have produced a
  red CI/pre-commit state on day one, which is worse than no coverage.
- **What this means today**: `ruff check`, `black --check`, `mypy`, and
  the GitHub Actions `lint`/`typecheck`/`test` jobs look at `src/` and
  `tests/`, plus one explicit exception added in Milestone 2:
  `regime-trader/broker/alpaca_client.py` (new code, not pre-existing —
  see [ADR-002](ADR/ADR-002-Market-Data.md) Decision 5). `src/features/`
  and `tests/features/` (Milestone 3), and `src/hmm/` and `tests/hmm/`
  (Milestone 4), fall under the same `src`/`tests` scoping as
  `src/market_data` — no new exception needed. Every other file
  under `regime-trader/` or `backtest/` still gets no automated
  lint/format/type coverage; pre-commit's Ruff/Black/MyPy hooks are scoped
  with `files: ^(src|tests)/|^regime-trader/broker/alpaca_client\.py$` for
  the same reason.
- **Owner / next step**: bringing the rest of `regime-trader/` and
  `backtest/` under this same tooling — likely requiring a one-time
  formatting/lint-fix pass reviewed on its own, separate from any
  behavioral change — is future work, not yet assigned to a specific
  build-order item above. Whoever picks it up should update this note and
  [02_TECHNICAL_PLANNER.md](../02_TECHNICAL_PLANNER.md)'s build order
  rather than silently expanding tool scope in an unrelated PR.
- **Dependency separation**: `pyproject.toml` declares `regime-trader/`'s
  full runtime dependency set (pandas, numpy, scipy, hmmlearn, torch,
  transformers, ta, alpaca-py) under the optional `trading` extra, a
  narrower `market-data` extra (pandas, numpy, pyarrow, duckdb, alpaca-py)
  for `src/market_data` specifically — see
  [ADR-002](ADR/ADR-002-Market-Data.md) Decision 4 — and a `features`
  extra (pandas, numpy, ta) for `src/features`, which depends on
  `market_data.models`/`market_data.validation` at import time but not on
  `market_data`'s heavier storage/provider dependencies — see
  [ADR-003](ADR/ADR-003-Feature-Engineering.md) — and an `hmm` extra
  (pandas, numpy, scipy, hmmlearn) for `src/hmm`, which depends on
  `features.feature_vector`/`features.pipeline` at import time but never
  on `market_data` directly — this package never touches a raw bar, only
  `FeatureVector`s — see [ADR-007](ADR/ADR-007-HMM-Design.md). None of
  `trading`, `market-data`, `features`, or `hmm` is a base dependency of
  `src/common`; installing the foundation package alone
  (`pip install -e .` or `pip install -e ".[dev]"`) never pulls in any of
  them.

## Resolved gaps

### `broker/alpaca_client.py` — historical bar fetching (was item 2)
Closed in Milestone 2. `regime-trader/broker/alpaca_client.py`'s
`AlpacaMarketDataClient` satisfies `main.py.MarketDataProvider` as a thin
adapter over the new `market_data` package's `AlpacaHistoricalProvider`
— see [ADR-002](ADR/ADR-002-Market-Data.md) Decisions 1 and 5 for the
full design, and `tests/regime_trader/test_alpaca_client_adapter.py` for
the contract test verifying the ascending-index/exact-columns/no-NaN-gaps
requirements this gap's entry originally specified. `main.py` now
constructs `AlpacaMarketDataClient()` in place of the previous
`_NotYetImplemented(...)` placeholder.

*(the remaining open items above keep their original numbers 1, 3–6 — not
renumbered, to avoid rippling through every cross-reference to them
elsewhere in this handbook; see this file's own header note)*
