# ADR-017: Memory Loop Design

**Status**: Accepted
**Date**: 2026-07-14
**Milestone**: [9 — Adaptive Learning / Memory Loop](../../../../PROJECT_STATUS.md)

## Context

ADR-016 froze `ExperienceRecord` and `LearningDecision` before `src/memory/`
existed. This record covers the implementation decisions made building
against that freeze: how experience is actually stored, which algorithm
computes a `LearningDecision`, how the two are wired together, how shadow
recommendations get compared against production, and how all three are
benchmarked — the same category of decision ADR-009, ADR-011, ADR-013, and
ADR-015 recorded for Milestones 5 through 8.

Per explicit product-owner direction on review of ADR-016, Milestone 9 was
built in three explicit phases, each independently verified before the
next began — a stricter version of Milestone 8's two-phase build:

1. **Phase A — Experience Store only.** No learning. Prove serialization,
   append-only semantics, and deterministic replay before any bandit code
   exists.
2. **Phase B — Contextual bandit.** Only once Phase A's store was
   verified: `ThompsonSamplingPolicy` and `MemoryService`, producing real
   shadow `LearningDecision`s. Still never wired to production.
3. **Phase C — Evaluation.** Only once Phase B's recommendations existed:
   comparison reporting between production and shadow decisions. Still no
   production influence — evaluation reads history, it doesn't act on it.

## Decision

### 1. `ExperienceStore`: two implementations, one Protocol

`InMemoryExperienceStore` (pure in-process) and `JsonlExperienceStore`
(file-backed, append-only, one JSON object per line with sorted keys for
byte-for-byte deterministic output) both implement `memory.interfaces.
ExperienceStore`. `JsonlExperienceStore` composes `InMemoryExperienceStore`
rather than duplicating its indexing logic — file I/O and in-memory
indexing are separate concerns. Loading (`JsonlExperienceStore.load`)
follows the load-or-init pattern every other durable state file in this
codebase uses: a missing file is a legitimate first-run state, not an
error, matching `05_MEMORY_ENGINEER.md`'s coding standards. Neither
implementation exposes a mutation or deletion method — the Experience
Store is an immutable, append-only historical log by construction, not
just by convention, directly per the user's stated priority: separating
`ExperienceRecord` (immutable log) from `LearningDecision` (the learner's
evolving opinion) is "the most important design decision" in this
milestone.

### 2. Single-writer persistence, no concurrency guard

`JsonlExperienceStore` assumes exactly one process appends to a given
path at a time, the same assumption `data/trade_context_db.json` made
before it. This is a deliberate continuation, not an oversight — adding
file locking or a real concurrent-writer story is out of scope until a
concrete multi-writer need exists (there is currently exactly one
producer of experience: a backtest replay or, eventually, a live trading
loop, never both at once against the same path).

### 3. Contextual bandit: Thompson Sampling over Beta posteriors, adapted not ported

`BetaArm` and `ThompsonSamplingPolicy` reuse the exact reinforcement-
learning formulation `regime-trader/core/learning_engine.py` already
validated (see [Architecture/Reinforcement Learning Memory Loop.md](../Reinforcement%20Learning%20Memory%20Loop.md)):
`alpha += 1` on a win, `beta += 1` on a loss, `posterior_mean = alpha /
(alpha + beta)`, and a Thompson-Sampling draw (`random.Random.betavariate`,
never `posterior_mean` directly) so under-observed arms still get
explored. What's new: `BetaArm` is mutable by explicit, documented design
(matching `backtest.portfolio.PortfolioEngine`'s precedent for "the one
place with genuine state to hold across calls"), the bucketed context is
narrowed to `(strategy_id, regime_id)` per ADR-016 Decision 2, and every
sampling call takes a caller-supplied `random.Random` rather than reading
module-level global state — the same "explicit over implicit" dependency-
injection convention `common.time.Clock` already established for
non-deterministic inputs.

### 4. `recommended_allocation`: a scaling model, not an independent one

`recommended_allocation = production_allocation * sampled_weight`, where
`sampled_weight` is the Thompson Sampling draw (itself in `[0, 1]` since
that's the Beta distribution's support). This means the bandit only ever
scales production's own allocation down (or leaves it close to unchanged
for a strong posterior) — it never independently proposes a larger
allocation than production chose, a direct, structural extension of
invariant #5 ("every strategy is long-only") into shadow territory: even
a hypothetical recommendation stays inside the bound production already
respected. This was also the simplest model consistent with the user's
own worked example ("Current allocation: 0.70 → Bandit recommendation:
0.63") without requiring an independent position-sizing formula this
milestone has no grounded basis for.

### 5. `confidence`: derived from sample size, not posterior variance directly

`confidence = sample_size / (sample_size + confidence_smoothing)`
(`confidence_smoothing` defaults to 10.0, tunable via `MemoryConfig`).
This was chosen over a variance-derived confidence (e.g., from the Beta
posterior's own variance formula) for the same reason the bandit itself
was chosen over LightGBM: simpler, and directly explainable in
`LearningDecision.rationale` without needing to unpack a statistical
formula for a reader who isn't a statistician. It also matches exactly
what the Standards doc already committed to: "confidence... expected to
reflect posterior certainty (e.g., derived from accumulated sample
size)."

### 6. `MemoryService`: a thin, sanctioned entry point

`record_experience` appends to the store, then updates the policy, in
that order — a policy update never happens for an experience that failed
to persist. `recommend` is pure delegation to the policy. This mirrors
every other milestone's "one sanctioned entry point, everything else is
composable internals" pattern (`RiskService.decide`, `BacktestEngine.run`,
`ExecutionService.decide`) even though, unlike those, `MemoryService`
itself contains almost no logic — the logic lives in `ThompsonSamplingPolicy`
and the store implementations, which remain independently swappable
behind their own Protocols.

### 7. Evaluation: comparison only, with self-consistency validation

`memory.evaluation.evaluate` takes paired `(LearningDecision,
ExperienceRecord)` tuples and computes `agreement_rate` (fraction within
a tolerance, default `0.05`), signed and absolute `mean_drift`,
`simulated_pnl_total` (realized P&L linearly rescaled from
`production_allocation` to `recommended_allocation` — the simplest
defensible approximation without a real counterfactual position-sizing
simulator), `simulated_improvement`, a `cumulative_regret` series (bandit-
literature sign convention: counterfactual reward minus chosen-action
reward, positive means production left money on the table relative to the
learner), and `mean_confidence`. Every pair is validated for internal
consistency (matching symbol/strategy_id/regime_id/production_allocation)
before being used — a caller that mispairs a decision with the wrong
trade's outcome gets a loud `ValueError`, not a silently wrong report.
`evaluate` and `generate_evaluation_report` never mutate an
`ExperienceStore` or a `LearningPolicy` — they only read.

### 8. Benchmark methodology: three new categories, all pure in-memory

Per explicit request, this milestone adds `insert_ms_per_call`,
`update_ms_per_call`, and `recommend_ms_per_call` to the benchmark
history (`benchmarks/v0.9-memory-loop.json`), following the same
methodology as `tests/risk/test_performance.py`: a `pytest.mark.performance`
scenario asserting a generous CI-safe threshold, re-run standalone with
`resource.getrusage` for the checked-in precise numbers.
`JsonlExperienceStore.append`'s file I/O is deliberately excluded — its
latency is dominated by filesystem/OS behavior, not this package's logic,
consistent with no prior milestone separately benchmarking disk-write
cost. Measured peak memory (34.65mb) is far below every prior milestone's
~148-156mb — not a methodology inconsistency, but the direct consequence
of `memory` having zero transitive third-party dependencies (see
ADR-016's `pyproject.toml` note): no numpy/pandas/scipy/hmmlearn import
overhead to pay for.

## Consequences

- The three-phase build gave the shadow-mode guarantee three independent
  checkpoints to hold at, not one: Phase A proves the log is trustworthy
  before anything learns from it, Phase B proves the learner is
  deterministic and bounded before anything compares against it, and
  Phase C proves comparison is possible without ever touching production.
- `ExperienceRecord`/`LearningDecision`'s separation (ADR-016) plus this
  ADR's append-only store and thin service layer together mean the
  Experience Store can be pointed at a live trading loop's real trade
  closures later with no change to `store.py`, `bandit.py`, or
  `service.py` — only a new producer of `ExperienceRecord`s.
- `recommended_allocation`'s scaling-model design (Decision 4) makes a
  future "let the bandit propose allocations independently of production"
  change a visible, reviewable widening of this specific formula, not a
  silent behavior change buried in a larger diff.
- Trade-off, accepted: `confidence`'s sample-size-based formula (Decision
  5) is a simpler proxy than a true posterior-variance-derived confidence
  interval, and could misrepresent a context that has many samples but
  genuinely ambiguous outcomes (near-50/50 win rate) as more "confident"
  than it statistically is. Acceptable for a shadow-only milestone whose
  purpose is comparison, not production sizing; revisit if Milestone 9's
  evaluation reports (Decision 7) show this proxy diverging meaningfully
  from a variance-based measure once real experience accumulates.
- `simulated_pnl`'s linear-rescaling assumption (Decision 7) is a real,
  named approximation, not a simulation of what actually would have
  happened — slippage, liquidity, and risk-limit interactions at a
  different position size are all ignored. Good enough for a first-pass
  "is the learner directionally worth trusting" signal, not for anything
  resembling a backtest-grade counterfactual.

## Alternatives Considered

- **Compute `confidence` from the Beta posterior's variance directly**
  (`1 - normalized_stddev`, or similar) — rejected per Decision 5: harder
  to explain in a non-empty `rationale` string, and the sample-size proxy
  already satisfies the Standards doc's own suggested approach.
- **Let `recommended_allocation` be computed independently of
  `production_allocation`** (e.g., `recommended_allocation =
  posterior_mean` alone) — rejected per Decision 4: loses the
  long-only-consistent bound production_allocation already gives, and
  doesn't match the user's own worked example of the bandit *scaling*
  production's choice rather than replacing it outright.
- **Add file locking to `JsonlExperienceStore` for multi-writer safety**
  — rejected for this milestone per Decision 2: no concrete multi-writer
  scenario exists yet (backtest replay and live trading never write to
  the same experience log simultaneously today); adding it now would be
  unjustified complexity ahead of a demonstrated need.
- **Skip Phase C (evaluation) for this milestone, defer it to Milestone
  10 or later** — considered, not adopted: the user's own three-phase
  instruction explicitly scoped evaluation into Milestone 9, and without
  it there is no way to answer "is the learner worth trusting yet" at
  all — the entire point of shadow mode is to accumulate an answerable
  version of that question.
- **Benchmark `JsonlExperienceStore.append`'s file I/O as the "insert"
  number** — rejected per Decision 8: every other package's benchmark in
  this handbook measures pure in-memory logic (no I/O on the happy path);
  measuring disk-write latency would conflate this package's own
  performance with filesystem/OS variance, the same reasoning that kept
  I/O out of every prior milestone's benchmark.
