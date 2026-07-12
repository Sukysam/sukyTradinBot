# ADR-005: Add Provenance to the FeatureVector Contract (v1 → v2)

**Status**: Accepted
**Date**: 2026-07-12
**Milestone**: Between [3 — Feature Engineering Platform](../../../../PROJECT_STATUS.md)
and 4 — a second hardening pass on Milestone 3's deliverable, immediately
following [ADR-004](ADR-004-FeatureVector-Contract-Freeze.md), before
Milestone 4 begins.

## Context

[ADR-004](ADR-004-FeatureVector-Contract-Freeze.md) froze `FeatureVector`'s
shape and laid out a versioning policy, but the shape it froze had no way
to answer "exactly what produced this vector" after the fact. A consumer
holding a `FeatureVector` from a backtest or a training run had `metadata`
carrying an ad hoc, duplicated `pipeline_version` (present both as the
top-level `version` field and again inside `metadata["pipeline_version"]`
— itself a small wart ADR-004's own Standards document had already
flagged rather than fixed) and a free-text `source`, but nothing tying a
vector to *which version of each individual feature's formula* computed
it. Milestone 4 is about to train and run inference against this
pipeline's output; without that link, there is no way to later confirm a
live inference vector was computed by the same feature definitions a
model was trained against — exactly the kind of silent-drift risk that
undermines reproducible backtests, experiment traceability, and model
audits.

## Decision

`FeatureVector` gains a new required field, `provenance: Provenance`,
where `Provenance` is a new frozen dataclass:

```
Provenance
    pipeline_version: str
    manifest_version: str
    feature_versions: Mapping[str, int]
    generated_at: datetime
    source_dataset: str
```

`pipeline_version` and `metadata["pipeline_version"]`'s duplication is
resolved by removing both the standalone `FeatureVector.version` field and
`metadata["source"]`/`metadata["pipeline_version"]` — `provenance` is now
the one place this information lives. `feature_versions` is `{feature_name:
FeatureSpec.version}` for exactly the features present in that vector,
validated at construction to cover exactly `feature_names` — a consumer
can now confirm, per vector, that every feature was computed by the
formula version it expects. `generated_at` is wall-clock computation time
(distinct from `timestamp`, the bar's market time), sourced from an
injected `common.interfaces.Clock` (`FeaturePipeline.__init__(...,
clock: Clock | None = None)`, defaulting to `SystemClock()`), following
the same dependency-injection pattern established in Milestone 1/2 rather
than calling `datetime.now()` internally. `source_dataset` replaces the
old free-text `source` parameter under a name that matches what it's
actually for — a dataset identifier or cache key a caller can use to trace
a vector back to what was replayed to produce it.

Because this changes required fields on an already-frozen contract, per
ADR-004's own versioning policy this is a breaking change:
`pipeline.PIPELINE_VERSION` bumps from `"1"` to `"2"`.

## Consequences

- A model trained against a set of `FeatureVector`s can record their
  `provenance.feature_versions` snapshot alongside the trained model
  artifact; inference-time vectors can be compared against that snapshot
  to detect drift before it silently corrupts predictions — the exact
  capability Milestone 4's model-store design (Known Gaps item 3) will
  need.
- `pipeline_version`/`source` no longer exist in two places that could
  independently drift — `provenance` is the one canonical home, resolving
  the duplication ADR-004's Standards document had only documented, not
  fixed.
- `FeaturePipeline` now takes an optional `clock` parameter, making
  `generated_at` deterministically testable (`common.time.FixedClock`)
  the same way every other time-dependent component in this codebase
  already is — consistent with, not a special case of, the DI pattern
  from Milestone 1.
- One wall-clock read per `compute_series` call, not per vector — every
  vector produced by one call shares a `generated_at` and, since
  `Provenance` is immutable, the same `Provenance` instance, avoiding
  redundant allocation across a potentially large batch (matching the
  performance discipline established in
  [ADR-003](ADR-003-Feature-Engineering.md)'s Verification note).
- Trade-off, accepted: every existing call site constructing or reading a
  `FeatureVector` had to change (this landed before Milestone 4 started,
  so the actual blast radius was `src/features/` and `tests/features/`
  only — zero external consumers existed yet, which is exactly why this
  was worth doing now rather than after Milestone 4 begins depending on
  the old shape).
- `manifest_version` currently duplicates `manifest.MANIFEST_SCHEMA_VERSION`
  rather than a content hash of the manifest itself — acknowledged in
  `Provenance`'s own docstring as a deliberate choice, not an oversight:
  the manifest's actual content at any point in time is already fully
  reconstructable from `feature_versions` plus checked-in git history,
  so a second, duplicate content-versioning scheme isn't justified yet.

## Alternatives Considered

- **Put this information in `metadata` instead of a new structured field**
  — rejected: `metadata` is documented (Standards/FeatureVector
  Contract.md) as a free-form, only-loosely-typed bag consumers must
  tolerate unknown keys in. `feature_versions` in particular needs a
  guaranteed shape (`Mapping[str, int]`, keys matching `feature_names`,
  validated at construction) that a free-form mapping can't enforce —
  provenance information a consumer is expected to actually rely on for
  reproducibility belongs in a validated field, not an untyped bag.
- **Keep `source` as free text and add `source_dataset` alongside it** —
  rejected as redundant: nothing in this platform used `source` for
  anything other than what `source_dataset` now describes; keeping both
  would just reintroduce the same two-places-for-one-fact problem this
  ADR exists to remove.
- **Avoid the breaking change by making `provenance` optional
  (`Provenance | None = None`)** — rejected: an optional provenance field
  would let a caller construct a `FeatureVector` with no traceability at
  all, silently defeating the entire point of this change. Every
  `FeatureVector` this platform produces goes through `FeaturePipeline`,
  which can always populate `provenance` fully — there is no legitimate
  case for a vector without it.
