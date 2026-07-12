# ADR-004: Freeze the FeatureVector Contract

**Status**: Accepted
**Date**: 2026-07-12
**Milestone**: Between [3 — Feature Engineering Platform](../../../../PROJECT_STATUS.md)
and 4 — hardens Milestone 3's deliverable before any consumer starts
depending on it.

## Context

Milestone 3 shipped `FeatureVector` and `FeaturePipeline` with the stated
goal that every future consumer (HMM, backtesting, adaptive learning,
NLP, risk) reads the same contract instead of each growing its own
feature-reading logic. That goal only holds if the contract itself stays
stable once consumers exist. Milestone 4 (HMM & Regime Detection) is
about to become the first real consumer, and once code outside
`src/features/` depends on `FeatureVector`'s field names, metadata keys,
and ordering behavior, an undocumented or silent change to any of them
becomes a cross-package bug that looks like a data problem in whatever
consumed it — not a data problem, a contract problem, and a far slower one
to diagnose. This was true the moment Milestone 3 shipped but hadn't yet
been made an explicit, binding rule; this ADR makes it one before that
first real dependency is created.

## Decision

`FeatureVector` — its required fields, metadata schema, feature-ordering
guarantees, versioning policy, and backward-compatibility rules — is now
a frozen, binding contract, documented in full at
[Standards/FeatureVector Contract.md](../../Standards/FeatureVector%20Contract.md).
Every future consumer relies on that document's guarantees rather than
reaching into `FeaturePipeline` or `FeatureRegistry` internals. Changes
to the contract follow the rules that document lays out: additive changes
(new features, new metadata keys, a single feature's own version bump)
require no contract-version change; anything that would change what an
existing field means, how vectors are ordered, or what a consumer can
assume about a required field requires bumping `PIPELINE_VERSION` and a
new ADR — never a silent in-place redefinition.

## Consequences

- Milestone 4 and every milestone after it has one place to check what
  `FeatureVector` guarantees, instead of inferring behavior from
  `pipeline.py`'s current implementation — which is exactly the kind of
  implicit coupling this freeze exists to prevent.
- A consumer that needs positional stability (e.g. a fixed-column
  training matrix) now has an explicit, documented answer — pass
  `feature_names` explicitly — rather than discovering the alphabetical-
  ordering behavior by reading source or, worse, by a silent column-shift
  bug the first time a new feature is registered.
- Adding a feature to the registry remains cheap and unblocked by this
  freeze — it's explicitly classified as a non-breaking, no-version-bump
  change. This freeze targets the *contract shape*, not feature-library
  growth, which is expected to continue throughout the project.
- Trade-off, accepted deliberately: a genuine breaking change to
  `FeatureVector` (e.g. a field rename) now costs more — a version bump,
  an ADR, and a defined migration path for every consumer that exists by
  then — than it would have cost to make silently today, before any
  consumer exists. That cost is the entire point: it is supposed to be
  cheap now and expensive later, and this ADR is filed specifically
  because "later" (Milestone 4) starts next.
- One acknowledged gap, not solved by this ADR: there is no automated
  check that `PIPELINE_VERSION` actually gets bumped when a breaking
  change lands — it's a code-review responsibility against the Standards
  document, not a test. Noted in that document rather than quietly
  assumed away.

## Alternatives Considered

- **Leave the contract implicit and re-derive it from `pipeline.py` as
  needed** — rejected: this is the status quo Milestone 3 shipped with,
  and it's exactly what makes a future silent change invisible until a
  downstream consumer breaks. Writing it down doesn't change today's
  behavior; it changes what "changing today's behavior without discussion"
  costs.
- **Version every field independently (field-level versioning) instead of
  one whole-contract `PIPELINE_VERSION`** — rejected as premature: no
  concrete need for independent field-level versioning has come up, and
  it would add real complexity (every consumer now needs per-field
  version negotiation) for a problem this platform doesn't have yet.
  `FeatureSpec.version` already gives per-feature semantic versioning
  where it's actually needed (a feature's own formula changing); a
  second, finer-grained versioning axis on top of that for the contract's
  own fields isn't justified until a real case for it exists.
- **Enforce the freeze with a runtime check (e.g. a schema-diff test
  comparing `FeatureVector`'s dataclass fields against a checked-in
  golden schema)** — considered as a stronger version of the "known gap"
  noted above, deferred rather than rejected outright: worth building
  once Milestone 4 exists as a real consumer to validate the check
  against, rather than speculatively now against zero consumers.
