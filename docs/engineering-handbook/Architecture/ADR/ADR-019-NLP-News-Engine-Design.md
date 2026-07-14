# ADR-019: NLP News Engine Design

**Status**: Accepted
**Date**: 2026-07-14
**Milestone**: [10 — NLP & Event Processing](../../../../PROJECT_STATUS.md)

## Context

ADR-018 froze `NewsSignal` before `src/nlp/` existed. This record covers
the implementation decisions made building against that freeze: how news
is ingested and deduplicated, how sentiment is scored, how the two are
wired together, how the pipeline is evaluated, and how it's benchmarked
-- the same category of decision ADR-017 recorded for Milestone 9's
Memory Loop.

Per explicit product-owner direction, Milestone 10 was built in three
independently-verified phases, mirroring Milestone 9's build order more
closely than any prior milestone has:

1. **Phase A — Ingestion.** Deterministic cleaning and deduplication into
   an internal `NewsItem`, with no sentiment model involved at all.
2. **Phase B — Sentiment.** A `SentimentScorer` Protocol with two
   implementations -- a dependency-free `DeterministicSentimentScorer`
   for tests and as an explicit fallback, and `FinBertSentimentScorer`,
   adapting the legacy `regime-trader/core/sentiment_engine.py` engine --
   producing the frozen `NewsSignal`.
3. **Phase C — Evaluation.** Read-only reporting: ingestion latency,
   deduplication rate, sentiment distribution, and processing throughput.
   No production influence, matching every prior milestone's evaluation
   phase.

## Decision

### 1. `NewsItemStore`: two implementations, one Protocol, idempotent by design

`InMemoryNewsItemStore` and `JsonlNewsItemStore` both implement
`nlp.interfaces.NewsItemStore`, mirroring `memory.store`'s
`InMemoryExperienceStore`/`JsonlExperienceStore` split (in-process vs.
file-backed, single-writer, load-or-init). The one structural difference:
`NewsItemStore.add` returns `bool` (`True` = newly stored, `False` =
duplicate no-op) rather than always appending -- deduplication on
`(source, source_id)` is this store's whole purpose, unlike the
Experience Store, which is append-only with no dedup concept at all. A
duplicate `add` on `JsonlNewsItemStore` writes nothing to disk, keeping
the file exactly one line per genuinely new story.

### 2. Deduplication scope: exact `(source, source_id)` match only

Per the Standards doc's own scope note, this milestone's deduplication is
deliberately narrow: redelivery protection (the same WebSocket event
arriving twice, e.g. after a reconnect), not fuzzy cross-source duplicate
detection (two different providers reporting the same real-world story
with different headlines and IDs). The latter is a genuinely harder NLP
problem with no reference implementation to ground it in, and was never
part of this milestone's brief.

### 3. `SentimentScorer`: batch-only Protocol, no single-headline method

`06_NLP_ENGINEER.md`'s existing acceptance criteria are explicit: "bursts
of headlines must go through `score_batch`, never a loop of `score()`
calls." This Protocol enforces that architecturally, not just by
convention -- there is no single-headline `score` method anywhere on the
Protocol, so a caller cannot fall into the anti-pattern even by accident.
`NlpService.build_signals` mirrors this: one method, no per-item overload.

### 4. Two `SentimentScorer` implementations, per explicit "swap implementations" direction

- **`DeterministicSentimentScorer`**: a caller-configured lookup (default
  result plus per-headline overrides), zero dependencies, zero inference
  cost. Every Phase B/C test in this milestone uses it. Also usable in
  production as an explicit "no model configured" fallback -- its default
  is neutral, not a fabricated opinion.
- **`FinBertSentimentScorer`**: adapts `regime-trader/core/
  sentiment_engine.py::SentimentEngine` closely -- same model
  (`ProsusAI/finbert`), same `id2label`-driven label-set validation
  (never hardcoded label order), same `MAX_SEQUENCE_LENGTH = 512`, same
  empty-batch-returns-empty-list short circuit. What's different:
  `torch`/`transformers` are imported lazily inside `__init__`, not at
  module level, so `nlp.sentiment` (and everything that imports it,
  transitively all of `nlp`) never requires those packages to be
  installed -- mirrors `execution.broker_adapter`'s isolation of the one
  module that imports the Alpaca SDK. A missing dependency raises
  `NlpError` at construction, not a bare `ImportError` at import time.

### 5. FinBERT-dependent tests are integration tests, gated and skipped gracefully

Per `06_NLP_ENGINEER.md`'s own acceptance criteria ("FinBERT-dependent
tests must be marked as integration tests, separate from the fast unit
suite"), `tests/nlp/test_sentiment_integration.py` is marked
`@pytest.mark.integration` (a new marker, registered in `pyproject.toml`
alongside the existing `performance` marker) and calls `pytest.importorskip
("torch")`/`("transformers")` at module level. This means the file
*skips*, not fails, in any environment without the `trading` extra
installed -- including this repository's own base CI matrix, which does
not install `torch`/`transformers` today. `src/nlp/sentiment.py`'s
`FinBertSentimentScorer` body is therefore not exercised by CI's default
test run; this is a known, deliberate, and previously-established pattern
(the same honesty this handbook already applies to Alpaca-credential-gated
tests), not an oversight -- see Known Gaps.

### 6. Entity extraction deferred; `entities` is always `()` in this milestone

The Standards doc's `entities` field explicitly allows an empty tuple.
`NlpService.build_signals` always sets `entities=()` -- no entity
extractor exists yet, and none was in this milestone's brief per the
technical lead's own Phase A/B/C breakdown (ingestion, sentiment,
evaluation -- no separate entity-extraction phase named). Building one is
future work, tracked the same way SHAP attribution is: named, scoped, not
assumed.

### 7. `signal_id` derived deterministically from `(source, source_id)`

`f"{item.source}:{item.source_id}"` -- simple, deterministic, and
sufficient given this milestone produces exactly one `NewsSignal` per
stored `NewsItem` (no re-scoring, no multiple signals per story). The
Standards doc deliberately left `signal_id` not-necessarily-equal to the
feed's own story ID for future flexibility (e.g. a re-scored signal after
a model upgrade), but nothing in this milestone needs that flexibility
yet.

### 8. Evaluation: three read-only report functions, no state mutation

`evaluate_ingestion` (deduplication rate, throughput, from a caller-
supplied sequence of `NewsItemStore.add` results plus a timing window),
`evaluate_sentiment` (label distribution, mean scores, optional
throughput), and `generate_evaluation_report` (plain-text summary,
matching `backtest.reporting.generate_report`'s and `memory.evaluation.
generate_evaluation_report`'s minimalism). None of the three call `add`
or `score_batch` themselves -- they only read results the caller already
produced, the same "comparison only, never mutates" property `memory.
evaluation` established.

### 9. Benchmark methodology: `DeterministicSentimentScorer` only

Ingest, dedup-check, and batch-sentiment-scoring latency are all
benchmarked against `InMemoryNewsItemStore`/`DeterministicSentimentScorer`
-- pure in-memory, no I/O, no real model. `FinBertSentimentScorer`'s real
inference latency is deliberately excluded, for the same reason
`JsonlExperienceStore.append`'s file I/O was excluded from Milestone 9's
benchmark: it isn't installed in the environment this benchmark runs in,
and its cost is dominated by model inference, not this package's logic.

## Consequences

- The three-phase build gave the shadow-mode guarantee three independent
  checkpoints, the same benefit Milestone 9's phasing provided: Phase A
  proves ingestion is deterministic and idempotent before anything scores
  it, Phase B proves scoring is swappable and batch-only before anything
  compares it, and Phase C proves evaluation is possible without ever
  touching production.
- The `SentimentScorer` Protocol's batch-only design makes a future
  regression to per-headline scoring (e.g. someone adding a convenience
  `score()` method and looping it) a visible, reviewable Protocol change,
  not a silent performance regression.
- `FinBertSentimentScorer`'s lazy import means `pip install -e .` (no
  extras) is sufficient to use every other part of `nlp` -- ingestion,
  deduplication, the deterministic scorer, and evaluation all work with
  zero new third-party dependencies, the same zero-dependency property
  `memory` already has.
- Trade-off, accepted: `FinBertSentimentScorer`'s real behavior is
  unverified by this repository's own CI today, since the `trading`
  extra (which provides `torch`/`transformers`) isn't installed there.
  The integration-test marker and `pytest.importorskip` guard make this
  an honest, visible gap (the test file always exists and always
  attempts to run) rather than a silently untested code path -- but it
  remains a real gap until CI or a maintainer's local environment
  actually exercises it.
- Deduplication's narrow `(source, source_id)`-only scope means two
  different providers reporting the same real story will produce two
  separate `NewsSignal`s today. Acceptable for this milestone (still
  shadow-mode, no production consumer to confuse), revisit if Milestone
  11's orchestration work finds this creates noisy or conflicting
  signals once multiple providers are actually wired in.

## Alternatives Considered

- **Give `SentimentScorer` both a `score` and `score_batch` method**,
  letting callers choose -- rejected per Decision 3: a convenience single-
  headline method invites the exact loop-calling anti-pattern
  `06_NLP_ENGINEER.md` warns against; omitting it entirely is a stronger
  guarantee than documentation alone.
- **Mock `torch`/`transformers` in unit tests to exercise
  `FinBertSentimentScorer`'s logic without real weights** -- rejected:
  mocking the tokenizer/model would test the mock's behavior, not
  FinBERT's, and could pass while the real integration is broken --
  exactly the "tests that don't test anything real" failure mode this
  handbook has avoided everywhere else (see the golden-dataset tolerance
  rationale in ADR-015 for the same underlying principle: prefer an
  honest gap to a false sense of coverage).
- **Attempt fuzzy cross-source deduplication (headline similarity,
  embedding distance) in Phase A** -- rejected per Decision 2: no
  reference implementation exists to ground it in, it's a genuinely
  harder problem than exact-ID redelivery protection, and nothing in
  this milestone's brief called for it.
- **Build a real (even simple, rule-based) entity extractor in Phase B**
  -- rejected per Decision 6: not in the technical lead's own phased
  breakdown for this milestone; the contract already tolerates
  `entities=()`, so there was no forcing function to build one now.
- **Benchmark `FinBertSentimentScorer` anyway, documenting expected
  values from prior knowledge rather than a real measurement** --
  rejected: this handbook's benchmark discipline (see every prior
  `benchmarks/*.json`) is "measured, not assumed" by design; a number
  not actually produced by running the code in this environment would
  violate that discipline more than omitting it entirely.
