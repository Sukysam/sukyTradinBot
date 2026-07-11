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

### 2. `broker/alpaca_client.py` — historical bar fetching
Satisfies `main.py.MarketDataProvider`: `get_ohlcv_history(ticker,
lookback_days) -> pd.DataFrame`. Must return an ascending-time-indexed
DataFrame with columns `['open','high','low','close','volume']` — the exact
contract `feature_engineering.build_feature_matrix` expects, currently
unchecked at the boundary. Blocks the entire structural loop, and blocks
backfilling real equity data for HMM training and regime-aware
backtesting. Owner: [03_BACKEND_ENGINEER.md](../03_BACKEND_ENGINEER.md).

### 3. A trained-HMM-model store
Satisfies `main.py.ModelStore`: `get_model(ticker) -> GaussianHMM`.
Persistence and refresh cadence for `hmm_engine.GaussianHMM` fits is **not
specified anywhere in the spec's Sec. 6 pipelines** — needs a design
decision, not just an implementation. This is also the blocker for
"online learning" of the HMM layer itself (today, online learning is
implemented only for the RL memory loop's bandit — see
[Architecture/Reinforcement Learning Memory Loop.md](Reinforcement%20Learning%20Memory%20Loop.md)).
Owner: [05_MEMORY_ENGINEER.md](../05_MEMORY_ENGINEER.md).

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

Items 1–4 above are (or, for item 4, will be) injected into
`RegimeTraderApp` in `main.py`'s `main()` function as
`_NotYetImplemented(missing_component_description)` instances, whose
`__getattr__` raises `NotImplementedError` the moment the structural loop
actually calls a method on it. This means:

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

## Resolved gaps

*(none yet — move an entry here, with the PR/date and a link to the
closing PR, when a gap above is fully implemented and matches its
`Protocol` contract or, for items 5–6, its target architecture doc)*
