# 01 — System Architect

## Mandate

Own the shape of the system: how the event-driven execution model (three
concurrent pipelines under one `asyncio` event loop) fits together, how
not-yet-built capabilities (adaptive allocation, SHAP attribution) plug in
without forcing rewrites of what already exists, and where the boundary
sits between every other role's territory.

## Capability ownership

| Capability | This role's responsibility |
|---|---|
| Event-Driven Execution | Full ownership — the three-pipeline shape, their independence, and their shared lifecycle |
| Alpaca Broker Integration | Shared with Backend Engineer — Architect owns the `Protocol` contract, Backend Engineer owns the implementation behind it |
| All other capabilities | Architect owns the *seams* between the owning role's module and the rest of the system, not the capability's internals |

## Owns

- `regime-trader/main.py` — `RegimeTraderApp`, the `Protocol` interfaces
  (`MarketDataProvider`, `ModelStore`, `SignalGenerator`), `StabilityFilter`,
  `EquityTracker`.
- The seams between `core/`, `broker/`, and `data/` — i.e., who is allowed
  to import whom.
- The decision of *where* a new capability lives (new module vs. extending
  an existing one), including where `core/attribution.py` (SHAP) and any
  adaptive-allocation model artifact will eventually live.

## Import direction (do not invert)

```
main.py
  ├── broker/*        (news_streamer, order_executor, alpaca_client [planned])
  ├── core/*           (hmm_engine, risk_manager, sentiment_engine, learning_engine,
  │                      signal_generator [planned], regime_strategies [planned],
  │                      attribution [planned])
  └── data/*           (feature_engineering)
```

`core/risk_manager.py` imports `data/feature_engineering.log_returns` — the
one sanctioned cross-import between those two layers, so the correlation
filter and the HMM feature matrix compute returns identically. Don't let
`broker/` import from `core/` (`news_streamer.py` is deliberately
transport-only). Don't let `core/` modules import `broker/` or `main.py`.
When `core/attribution.py` is built, it may import from `core/hmm_engine.py`
and `data/feature_engineering.py` (it explains their outputs) but must never
be imported by either — attribution is a consumer of the model layer, not a
dependency of it.

## Core responsibilities & workflows

1. **Interface stewardship.** Define and version every `Protocol` that
   crosses a role boundary before implementation starts on either side —
   this is what let `broker/order_executor.py` and `core/risk_manager.py`
   be built independently against `main.py`'s existing contracts.
2. **Pipeline integrity review.** For any PR touching `main.py`, confirm
   the three pipelines (structural loop, news listener, weekend cron)
   remain independently schedulable and that no new code introduces a
   blocking call inside an `async def` without `asyncio.to_thread`.
3. **Capability integration planning.** When a new capability (adaptive
   allocation, SHAP) moves from Planned to In Progress, produce the
   `Protocol` contract for it before any role begins implementation, and
   record it in [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md).
4. **Cross-role arbitration.** When two roles disagree about which owns a
   given piece of logic (e.g. "does position sizing live in Signal
   Orchestrator or Risk Manager"), the Architect makes the placement call
   and records the rationale in the relevant role files.

## Acceptance criteria (Definition of Done for this role's deliverables)

- Every new or changed `Protocol` has a docstring stating: the concrete
  implementation(s) expected to satisfy it, every method's contract
  (inputs, outputs, error conditions), and which role owns building each
  implementation.
- No PR merges that adds a synchronous blocking call inside
  `_structural_loop`, `_weekend_cron_loop`, or any coroutine reachable from
  them, without an `asyncio.to_thread` wrapper.
- Architecture diagrams in [Architecture/System Overview.md](Architecture/System%20Overview.md)
  and [Architecture/Data Flow.md](Architecture/Data%20Flow.md) are updated
  in the same PR as any change to pipeline shape or module boundaries —
  never left to drift.
- A capability moving status in the Capability Ownership Map (Master
  Charter) is accompanied by an updated `Protocol` definition if its
  implementation surface changed.

## Coding standards

Follow [Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md)
and [Standards/Coding Standards.md](Standards/Coding%20Standards.md) in
full. Architecture-specific additions:

- `Protocol` classes live at the top of the module that consumes them
  (see `main.py`'s pattern), not in a separate `interfaces.py` — the
  consumer's file is the natural place to find "what does this need."
- Every `Protocol` method gets a docstring even when the method signature
  looks self-explanatory; a `Protocol` is a promise to implementers who
  haven't seen the consuming code.
- Dataclasses that cross a `Protocol` boundary (`TradeDecision`) are
  `frozen=True` — a decision object should never be mutated after
  construction by any downstream consumer.

## Communication protocols

- Interface changes are announced in the PR description under a
  **"Breaking Contract Change"** heading if any existing implementer would
  need to change, even if none exists yet in-tree — a future implementer
  reading history should see the change was deliberate.
- Cross-role placement decisions ("this logic belongs in Signal
  Orchestrator, not Risk Manager") are recorded as a short rationale note
  appended to both affected role files' "Pitfalls" section, not just
  stated once in a PR comment that will be lost to history.
- When arbitrating a disagreement between two roles, respond within the
  same session/thread — don't let an architecture question block other
  roles' in-flight work silently.

## Must escalate

- Merging or resequencing the three pipelines (structural loop / news
  listener / weekend cron) — deliberately independent, not accidental.
- Any change to the `Protocol` signatures in `main.py`
  (`MarketDataProvider`, `ModelStore`, `SignalGenerator`) or to the planned
  `AttributionProvider` contract once it exists — these are relied on by
  code that may not exist yet, but changing them after downstream
  implementations land is a breaking change.
- Introducing a second event loop, a second process, or any change to how
  `EQUITY_STATE_PATH`/`LEARNING_WEIGHTS_PATH`/`TRADE_CONTEXT_DB_PATH` are
  resolved (relative-path assumptions ripple into
  [DevOps Engineer](12_DEVOPS_ENGINEER.md)'s deployment contract).

## Pitfalls specific to this seam

- `RegimeTraderApp.__init__` deliberately does **not** construct
  `asyncio.Event()` — it's created in `run()` because `__init__` executes
  before `asyncio.run()` starts a loop. Any new asyncio primitive follows
  this pattern.
- `_evaluate_and_submit` deliberately does **not** write to
  `trade_context_db.json` — that's `signal_generator.py`'s job, to avoid
  two writers racing on the same file. Preserve that single-writer
  invariant when `signal_generator.py` and, later, `core/attribution.py`
  land — attribution records should be appended by the same writer that
  owns the trade context entry, not a second file-writing path.
- Placement decision on record: **position sizing math lives in Signal
  Orchestrator** (it decides `notional_value` before the veto layer sees
  it); **position sizing limits live in Risk Manager** (it can only shrink
  or reject, never invent a size). Don't let a future PR blur this line by
  having the veto layer compute a "better" size instead of a multiplier.
