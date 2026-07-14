# ADR-018: Freeze the NewsSignal Contract

**Status**: Accepted
**Date**: 2026-07-14
**Milestone**: [10 — NLP & Event Processing](../../../../PROJECT_STATUS.md) (contract
only — no implementation in this record; see Context)

## Context

Milestone 9 established a pattern this record repeats one milestone
later: a working reference implementation already exists outside `src/`
— here, `regime-trader/core/sentiment_engine.py` (`SentimentEngine`,
FinBERT-backed, producing `SentimentScore`) and
`regime-trader/broker/news_streamer.py` (`NewsStreamer`, producing
`NewsItem` from Alpaca's news WebSocket) — and the question is how much
of it carries forward as-is versus gets adapted into this handbook's
contract-first, shadow-mode discipline.

Product-owner review gave explicit direction narrowing Milestone 10's
scope below what the uploaded architecture documents and
[PROJECT_STATUS.md](../../../../PROJECT_STATUS.md)'s own Milestone 10 row
imply at first read:

1. **Shadow mode again.** The uploaded documents suggested integrating
   sentiment fairly directly into trading logic. Rejected for this
   milestone: `NewsSignal` is recorded; the Strategy Engine remains
   completely unaware of it until Milestone 11 (Signal Orchestration)
   deliberately wires multiple decision sources together. Same boundary
   ADR-016 established for `LearningDecision`, applied to a second,
   independent signal source.
2. **Freeze first.** `NewsSignal` — one output type — is frozen and
   reviewed *before* `src/nlp/` is scaffolded, matching every milestone
   since Milestone 5.
3. **Infrastructure before the model, in three phases**, delaying FinBERT
   specifically: Phase 1 (ingestion, normalization, deduplication,
   storage — no sentiment model), Phase 2 (the sentiment model itself),
   Phase 3 (attribution). This mirrors Milestone 9's three-phase build
   (Experience Store → bandit → evaluation) and Milestone 8's two-phase
   build (replay → metrics) — the same "prove the infrastructure is
   stable before layering a model on top" discipline, applied a third
   time.

## Decision

`nlp.models.NewsSignal` — `signal_id`, `source_id`, `source`, `symbols`,
`entities`, `headline`, `published_at`, `processed_at`,
`sentiment_positive`, `sentiment_negative`, `sentiment_neutral`,
`sentiment_label`, `model_version`, `metadata` — is frozen as a binding
contract, documented in full at
[Standards/NewsSignal Contract.md](../../Standards/NewsSignal%20Contract.md),
*before* `src/nlp/` is scaffolded.

The contract **adapts, not ports**, the two legacy shapes it's grounded
in:

- **From `SentimentScore`** (`text`, `positive`, `negative`, `neutral`,
  `label`): the three-probability-plus-label shape and its `[0.99, 1.01]`
  sum tolerance are kept identical — that tolerance reflects real
  observed FinBERT softmax floating-point behavior, not an arbitrary
  choice, so there was no reason to re-derive it. What's new:
  `sentiment_label` must be validated at construction to actually equal
  the argmax of the three scores, promoting "the label always matches
  the highest score" from something only true because the reference
  engine happens to compute it that way, into a type-level guarantee
  independent of any particular implementation.
- **From `NewsItem`** (`id`, `headline`, `summary`, `symbols`, `source`,
  `created_at`): `headline`, `symbols`, and `source` carry over directly
  (renamed `id` → `source_id`, `created_at` → `published_at` for clarity
  against the new `processed_at` field). `summary` is deliberately **not**
  promoted to a required field — `06_NLP_ENGINEER.md`'s own documented
  pitfall notes FinBERT here is calibrated against headlines specifically,
  and `NewsItem.summary` can legitimately be empty (`news.summary or ""`),
  so committing to it as a guaranteed, non-empty contract field would be
  dishonest about what the reference model actually promises.
- **New, not present in either legacy shape**: `signal_id` (this
  contract's own identity, distinct from the raw feed's story ID, since
  one `NewsSignal` exists per de-duplicated *processed* story, and
  dedup/processing is Milestone 10's own pipeline concern);
  `processed_at` (causal traceability — must be `>= published_at`,
  extending invariant #1's no-look-ahead spirit to a signal that can only
  exist after its source material does); `entities` (entity extraction is
  new to this milestone, independent of the feed's own `symbols` tagging
  — no overlap or de-duplication rule between the two is required);
  `model_version` (traceability, matching `RegimeState.model_version`/
  `LearningDecision.model_version`'s existing pattern — absent from the
  legacy engine entirely, since it never needed to distinguish which
  model version produced a given score).

Two properties are enforced at the type level, not left to documentation:

1. **The shadow-mode guarantee.** No code path in Milestone 10
   constructs a `StrategyDecision`, `ExecutionDecision`, or `OrderIntent`
   from a `NewsSignal`. `strategy` gains no new dependency on `nlp` in
   this milestone; `nlp` may read already-frozen contracts if useful
   (none currently needed), never the reverse.
2. **`sentiment_label` consistency.** Must equal the argmax of the three
   probability fields — see above.

`NewsSignal` is the *only* frozen output of this milestone. The pipeline
stages that produce it — ingestion, cleaning, deduplication — are
deliberately left unfrozen internal detail, the same way
[ADR-013](ADR-013-Execution-Layer-Design.md) left `ExecutionContext`/
`FeatureSnapshot` unfrozen: "execution contracts describe trading intent,
not market observations" generalizes here to "the frozen contract
describes a processed signal, not how it was assembled."

## Consequences

- Whoever implements Milestone 10 has one document to build against
  before writing `src/nlp/`'s first line — how news is ingested, how
  deduplication works, and which entity-extraction method is used are
  all free to be designed and iterated on, because none of that is what
  this freeze constrains.
- The shadow-mode guarantee makes "NLP doesn't affect production" a
  property reviewable in a PR diff (does any new import edge exist from
  `strategy`/`risk`/`execution` into `nlp`?), the same audit `strategy`
  already gets against `memory` per ADR-016.
- The three-phase build order (ingestion → sentiment → attribution) means
  Phase 1 can ship and be verified — deterministic, tested ingestion and
  deduplication — without a single FinBERT inference call, the same way
  Milestone 9's Phase A verified the Experience Store before any bandit
  code existed.
- `sentiment_label`'s argmax-consistency check makes a future,
  differently-behaved sentiment model's output impossible to represent
  incorrectly as a `NewsSignal` — a model that produces an inconsistent
  label/score pairing fails loudly at construction, not silently later.
- Trade-off, accepted: like ADR-016, this freeze is more speculative than
  one written against an existing `src/` implementation would be — no
  `src/nlp/` code exists yet to have grounded these field choices in real
  usage. The legacy `sentiment_engine.py`/`news_streamer.py`
  implementations partially substitute for that grounding, but they
  predate this handbook's contract discipline and were never reviewed
  against it.

## Alternatives Considered

- **Integrate `NewsSignal` (or raw sentiment scores) directly into
  `StrategyDecision` computation in this milestone**, matching the
  uploaded architecture documents' original sequencing — rejected per
  explicit direction: shadow mode first, the same reasoning ADR-016
  applied to the Memory Loop. Milestone 11 is where multiple decision
  sources are deliberately allowed to converge.
- **Build FinBERT scoring first, ingestion infrastructure second** —
  rejected per explicit direction: infrastructure (ingestion, cleaning,
  dedup, storage) should be provably stable before a model is layered on
  top, the same "prove the plumbing before the model" discipline
  Milestone 9's Phase A → Phase B ordering already established.
- **Include `summary` as a required, non-empty `NewsSignal` field** —
  rejected: the reference `SentimentEngine` is calibrated against
  headlines, and `NewsItem.summary` is legitimately sometimes empty;
  requiring it would misrepresent what any real implementation can
  honestly guarantee. A caller that wants to carry summary text through
  can use `metadata`.
- **Freeze `entities` to require non-empty output** — rejected: entity
  extraction may reasonably find nothing in a given headline (e.g. "Fed
  raises rates" mentions no company), and Phase 1/Phase 2 may ship before
  entity extraction exists at all; requiring non-empty output would force
  either a fabricated placeholder or blocking Phase 1/2 on Phase 3's
  scope, neither acceptable.
- **Skip the `sentiment_label`-matches-argmax validation, trusting the
  caller** — rejected: every other decision-shaped contract in this
  handbook enforces its cross-field invariants at construction
  (`TradeRecord.holding_period`, `ExperienceRecord.won`), and a
  reference implementation change (e.g. a different label-selection
  policy) that silently desynced label from score would otherwise be
  invisible until a much harder-to-diagnose downstream failure.
