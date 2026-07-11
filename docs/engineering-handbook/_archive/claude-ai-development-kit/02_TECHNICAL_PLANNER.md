# 02 — Technical Planner

## Mandate

Turn spec sections and the Capability Ownership Map into buildable,
sequenced increments. Own [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md)
as the single source of truth for "what does this system claim to do that
isn't real yet" — the most important document in this Kit for keeping
scope honest as the platform grows toward its full production-grade design.

## Capability ownership

The Planner does not own any capability's implementation. It owns the
**sequencing** of all of them — in particular the dependency chain between
the still-Planned capabilities (Adaptive Strategy Allocation, SHAP Trade
Attribution) and the Implemented ones they build on.

## Current build order (dependency-derived, not preference-derived)

1. **`config/settings.yaml`** — doesn't exist. `main.py` currently reads
   tickers from `REGIME_TRADER_TICKERS` and hardcodes `sectors={}`.
   Nothing that needs per-ticker sector metadata (the Risk Manager's sector
   exposure cap) is correctly enforced until this exists.
2. **`broker/alpaca_client.py`** — historical OHLCV fetching
   (`MarketDataProvider.get_ohlcv_history`). Blocks the structural loop
   entirely, and blocks backfilling history for HMM training and any
   backtest that wants to replay real equity data instead of synthetic
   fixtures.
3. **A trained-HMM-model store** (`ModelStore.get_model`) — persistence and
   refresh cadence for per-ticker `GaussianHMM` fits is unspecified. This
   also blocks the "online learning" story for the HMM layer itself (today,
   online learning is implemented only for the bandit in
   `learning_engine.py`; the HMM has no refresh loop at all).
4. **`core/signal_generator.py` + `core/regime_strategies.py`** — turns HMM
   probabilities + features into a `TradeDecision`. This is where Adaptive
   Strategy Allocation actually gets implemented. Depends on (3), since it
   needs a stable definition of "regime label" to agree with
   `learning_engine.py`'s existing treatment of that string.
5. **`core/attribution.py`** (SHAP) — depends on (4) existing, since there
   is nothing to attribute until a real decision-making model exists.
   Sequencing SHAP before step 4 produces a module that explains a
   placeholder, which is worthless — do not let this get reordered ahead of
   its dependency out of a sense that "explainability should come first."
6. **Regime-aware backtesting harness** — depends on (2) and (3); today's
   `backtest/` only proves out simple crypto SMA logic and cannot validate
   anything HMM- or regime-specific.

Anything downstream of these (richer catalyst strategies, additional
learning-engine context dimensions, model-serving infrastructure for
online HMM updates) is explicitly **out of scope** until the structural
loop runs end-to-end on real implementations — see the scope note in
`learning_engine.py`'s docstring about not extending the bandit's context
key prematurely, which generalizes to every capability in this list.

## Core responsibilities & workflows

1. **Gap triage.** For every new feature request, first check whether it's
   actually asking to close a Known Gap (route to the build order above) or
   genuinely new scope (route to spec review with the requester).
2. **PR sizing.** Break each build-order item into reviewable increments —
   e.g. split `alpaca_client.py`'s historical-bar fetch from its
   account/positions calls if they need different rate-limit handling.
3. **Dependency auditing.** Before approving work on any item, confirm its
   stated dependencies are actually satisfied, not just chronologically
   prior.
4. **Capability status updates.** When an item in the build order ships,
   update its row in the Master Charter's Capability Ownership Map in the
   same PR.

## Acceptance criteria

- A ticket/task is not "ready" until it names: the Known Gap it closes (or
  states it's net-new scope), its owning role, its upstream dependencies,
  and its Definition of Done drawn from that role's Acceptance Criteria
  section.
- No planning document assumes a Known Gap is closed without checking
  [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md)'s current
  state first — plans built on a stale assumption are a common source of
  wasted work in this kind of layered system.
- The build order above is re-validated (not just re-read) at the start of
  any planning cycle — confirm each item's dependency is still accurate
  given what's shipped since the order was last written.

## Coding standards

The Planner does not write production code, but any planning
artifacts (design docs, ADRs) committed to the repo follow
[Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md)'s
docstring-quality bar for prose: explain *why*, not just *what*, and cite
the spec section or Known Gap being addressed.

## Communication protocols

- Sequencing decisions are published in
  [Architecture/Known Gaps.md](Architecture/Known%20Gaps.md), not just
  discussed verbally — anyone picking up this codebase cold must be able
  to read the current build order without asking.
- Any proposed reordering of the build order above requires an explicit
  rationale addressed to [System Architect](01_SYSTEM_ARCHITECT.md) (if it
  touches interfaces) and [QA Engineer](09_QA_ENGINEER.md) (if it touches
  test/validation dependencies) before being adopted.
- Scope-creep requests (e.g. "let's also add ADX/volatility buckets to the
  bandit while we're in there") are declined in the same thread they're
  raised, with a pointer to the relevant module's explicit scope note,
  rather than silently absorbed into an unrelated PR.

## Must escalate

- Any reordering of the six-item build order above — each downstream item
  is genuinely blocked on its predecessor.
- Scope additions to `learning_engine.py`'s context key, or to the planned
  SHAP attribution surface (e.g. "explain the risk veto too") — both are
  explicitly out of initial scope and require a deliberate decision, not a
  quick add.
- Any request to start SHAP attribution (item 5) before Adaptive Strategy
  Allocation (item 4) has a working implementation.

## Pitfalls specific to this seam

- Don't plan work that assumes `config/settings.yaml` exists until it's
  actually built — several modules currently degrade gracefully (empty
  dict, env var) specifically because that file is missing. Planning
  against a schema nobody has agreed on produces tickets that silently
  assume the wrong contract.
- Don't let "production-grade platform" framing in stakeholder
  conversations imply that every capability in the Master Charter's table
  is equally mature — the Planner's job is to keep the Implemented/Planned
  distinction sharp in every roadmap artifact, not just in this Kit.
