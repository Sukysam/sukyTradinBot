# ADR-016: Freeze the LearningDecision and ExperienceRecord Contracts

**Status**: Accepted
**Date**: 2026-07-13
**Milestone**: [9 — Adaptive Learning / Memory Loop](../../../../PROJECT_STATUS.md) (contract
only — no implementation in this record; see Context)

## Context

Milestones 5 through 8 established a repeatable pattern: freeze a
milestone's output contract, reviewed, before its implementation exists.
Milestone 9 follows the same discipline, but starts from a different
place than any prior milestone: a working reference implementation
already exists, just not in `src/`.
[Architecture/Reinforcement Learning Memory Loop.md](../Reinforcement%20Learning%20Memory%20Loop.md)
and [05_MEMORY_ENGINEER.md](../../05_MEMORY_ENGINEER.md) document
`regime-trader/core/learning_engine.py` — a contextual multi-armed
bandit, Thompson Sampling over Beta(α, β) posteriors, context key
`(strategy, regime_label, rsi_bucket)`, weekly-batched updates from
`data/trade_context_db.json` into `data/learning_weights.json`. That code
is real, tested (per that document's own acceptance criteria), and
predates every contract this handbook has since frozen.

Product-owner review of Milestone 8 gave explicit direction on how much
of that reference design should carry forward as-is versus be adapted:
the underlying reinforcement-learning formulation (contextual bandit,
Thompson Sampling) is sound and should be reused, but the surrounding
architecture — SQLite-flavored ad hoc state files, no frozen contract, no
Protocol-based interfaces, no service-oriented package boundary, no
deterministic testing — predates `src/`'s own governance discipline and
should not be carried forward unexamined. Two further directives
narrowed Milestone 9's actual scope below what the reference design or
[PROJECT_STATUS.md](../../../../PROJECT_STATUS.md)'s own Milestone 9 row
implies at first read:

1. **Shadow mode only.** The learner records what it *would* have
   recommended; it never influences a real `StrategyDecision`,
   `ExecutionDecision`, or `OrderIntent` in this milestone. Comparison
   between production and shadow performance happens after a sufficient
   evaluation period, as a separate, later, explicitly-authorized step.
2. **Defer SHAP and defer LightGBM.** The uploaded architecture documents
   (predating this handbook's `src/` rewrite) proposed SHAP attribution
   and a LightGBM model as part of the initial Adaptive Learning build.
   Both are postponed: SHAP until the learner has accumulated enough real
   examples for attribution to be meaningful over a simple posterior
   summary, and LightGBM in favor of starting with the same
   deterministic, fast, explainable, incrementally-updatable bandit
   formulation the legacy code already validated. A more complex model is
   a decision to evaluate once the interfaces are stable, not a Milestone
   9 starting assumption.

Freezing `LearningDecision` and `ExperienceRecord` now, before `src/
memory/` exists, gives both directives a type-level guarantee rather than
a documentation promise — the same reasoning ADR-008 applied to
`StrategyDecision`'s "opinion, not order" boundary.

## Decision

Two types, both new to this handbook, are frozen together as
`memory.models.ExperienceRecord` and `memory.models.LearningDecision`,
documented in full at
[Standards/LearningDecision Contract.md](../../Standards/LearningDecision%20Contract.md),
*before* `src/memory/` is scaffolded.

1. **`ExperienceRecord`** is the atomic unit of the Experience Store —
   what `data/trade_context_db.json` was for the legacy design, given a
   frozen shape. It carries `symbol`, `strategy_id`, `regime_id`,
   `production_allocation` (the `StrategyDecision.allocation` actually
   acted on), `realized_pnl`/`realized_pnl_pct`/`won`, entry/exit
   timestamps and `holding_period`, a `source_run_id` for traceability
   back to a `backtest.models.ReplayRun` (or future live-session
   equivalent), and open `metadata`.

2. **`LearningDecision`** is the shadow recommendation — what `data/
   learning_weights.json`-derived confidence scaling was for the legacy
   design, given a frozen, auditable, per-decision shape instead of a
   compressed weight file. It carries the same `(symbol, strategy_id,
   regime_id)` context, both `production_allocation` and
   `recommended_allocation` (each `[0.0, 1.0]`, the same long-only bound
   `StrategyDecision.allocation` already enforces), a learner-native
   `confidence`, a `sample_size` so low-data recommendations are
   inspectable rather than silently trusted, a non-empty `rationale`
   (explicitly not SHAP — see Alternatives Considered), and a
   `model_version` for traceability.

Three properties are enforced at the type level or by architectural
convention, not left to documentation:

- **The shadow-mode guarantee.** No code path in Milestone 9 constructs
  an `OrderIntent`, `ExecutionDecision`, or `StrategyDecision` from a
  `LearningDecision.recommended_allocation`. `strategy`, `risk`, and
  `execution` gain no new dependency on `memory` in this milestone;
  `memory` may depend on their already-frozen contracts (reading
  `StrategyDecision`/`TradeRecord`-shaped data), never the reverse.
- **The learning context is `(strategy_id, regime_id)` only** — narrower
  than the legacy design's `(strategy, regime_label, rsi_bucket)`. Fewer
  dimensions means faster sample accumulation per arm; `symbol` is kept
  on `ExperienceRecord` for traceability but is not part of the bucketed
  context. Widening this is a deliberate, reviewed decision, per the
  reference design's own already-documented scope-boundary precedent.
- **`won` is derived and validated, not independently settable** —
  `realized_pnl > 0` (strict), matching the legacy design's own
  documented reward convention, checked at construction rather than
  trusted from a caller.

## Consequences

- Whoever implements Milestone 9 has one document to build against
  before writing `src/memory/`'s first line — which policy algorithm,
  how experience is persisted, and the exact service surface are all
  free to be designed and iterated on, because none of that is what this
  freeze constrains.
- The shadow-mode guarantee makes "the learner doesn't affect
  production" a property reviewable in a PR diff (does any new import
  edge exist from `strategy`/`risk`/`execution` into `memory`?), not
  something that has to be re-verified by reading implementation logic
  every time.
- `LearningDecision.rationale` being deliberately non-SHAP means the
  first implementation cannot silently under-deliver by shipping a vague
  or missing explanation and calling it "SHAP later" — a real, if simple,
  rationale is required from the first `LearningDecision` ever
  constructed.
- Trade-off, accepted: like ADR-008, this freeze is more speculative than
  a freeze written against an existing `src/` implementation would be —
  no `src/memory/` code exists yet to have grounded these field choices
  in real usage. The legacy `regime-trader/core/learning_engine.py`
  implementation partially substitutes for that grounding (its
  `TradeContext`/`BetaArm` shapes directly informed `ExperienceRecord`'s
  and `LearningDecision`'s fields), but it predates this handbook's
  contract discipline and was never itself reviewed against it.
- `ExperienceRecord`'s narrower-than-legacy context and `LearningDecision`'s
  shadow-only guarantee both make Milestone 9 strictly safer to ship than
  the reference design describes, at the cost of not yet delivering the
  reference design's actual behavior change (confidence-weighted position
  sizing). That gap is deliberate and named here, not accidental scope
  loss.

## Alternatives Considered

- **Port `core/learning_engine.py`'s `TradeContext`/`BetaArm` types
  directly into `src/memory/` with minimal changes** — rejected: those
  types are untyped-by-contract, live-influence position sizing
  immediately (no shadow mode), and bucket on an RSI feature this
  handbook's newer `FeatureVector`/`RegimeState` contracts don't
  guarantee is available at the point a recommendation is generated.
  Adapting the concepts while dropping the direct dependency on legacy
  shapes was explicit product-owner direction, not an independent
  judgment call.
- **Include SHAP-based attribution in `LearningDecision.rationale` from
  the start**, matching the uploaded architecture documents' original
  sequencing — rejected per explicit direction: SHAP needs a meaningfully
  sized experience history to explain anything real; building it before
  that history exists spends engineering effort explaining noise.
  [Architecture/SHAP Trade Attribution.md](../SHAP%20Trade%20Attribution.md)
  remains the target design for when this contract's `rationale` field
  is later asked to carry a real attribution record — an additive
  change, not a breaking one, since `rationale` is already typed as
  `str`.
- **Start with LightGBM (or another gradient-boosted model) as the
  learning policy**, also matching the uploaded documents — rejected per
  explicit direction: a contextual bandit is deterministic, fast to
  test, trivially explainable, and already validated by the legacy
  implementation; a more complex model is worth evaluating only once
  `memory`'s interfaces (this contract) are stable enough that swapping
  the policy underneath them is a contained change, not a redesign.
- **Freeze only `LearningDecision`, leaving `ExperienceRecord` as
  internal, unfrozen storage detail** (the way Milestone 7 deliberately
  left `ExecutionContext`/`FeatureSnapshot` unfrozen) — considered, not
  adopted: unlike those execution-time-only value objects,
  `ExperienceRecord` is itself an artifact intended to accumulate and be
  inspected/replayed across the system's lifetime (the Experience
  Store), closer in spirit to `BacktestResult.trade_log` than to a
  transient execution-context object — ADR-014's reasoning for freezing
  `trade_log` as part of the contract applies here too.
- **Bucket the learning context on `(strategy_id, regime_id, symbol)`**,
  preserving per-symbol granularity — rejected for the initial freeze:
  matches the reference design's own "extending the context boundary is
  a deliberate, reviewed decision" precedent: start narrow, widen only
  once a concrete need is demonstrated, not speculatively.
