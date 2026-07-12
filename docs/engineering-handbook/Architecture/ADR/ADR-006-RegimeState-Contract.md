# ADR-006: Freeze the RegimeState Contract

**Status**: Accepted
**Date**: 2026-07-12
**Milestone**: [4 — HMM & Regime Detection](../../../../PROJECT_STATUS.md)

## Context

Milestone 4's mandate, per the same discipline
[ADR-004](ADR-004-FeatureVector-Contract-Freeze.md) established for
`FeatureVector`, is to treat the HMM as an independent machine learning
service: it consumes only `FeatureVector`, it produces only a regime
call, and nothing about its internals — a fitted `hmmlearn.hmm.
GaussianHMM`, a normalizer, a raw posterior array — should ever be
something a downstream consumer holds onto. That requires a frozen output
contract to exist *before* implementation, not be inferred from
`RegimeService`'s return type after the fact, for the same reason
`FeatureVector` was frozen ahead of Milestone 4 itself: Milestone 5
(Strategy Engine) is the first real consumer, and a contract that's still
implicit when a real consumer arrives is a contract that's already too
late to freeze cheaply.

## Decision

`hmm.models.RegimeState` — `timestamp`, `symbol`, `regime_id`,
`confidence`, `transition_probability`, `model_version`,
`feature_pipeline_version`, `metadata` — is a frozen, binding contract,
documented in full at
[Standards/RegimeState Contract.md](../../Standards/RegimeState%20Contract.md).
`RegimeService.infer`/`infer_series` are the only functions that produce
it; nothing else in this codebase constructs a `RegimeState`. Every
future consumer (Strategy Engine, backtesting, risk) relies on that
document's guarantees rather than reaching into `RegimeService`,
`hmm.trainer`, `hmm.selector`, `hmm.inference`, or `hmm.persistence`.

## Consequences

- Milestone 5 has one place to check what a regime call guarantees,
  before a single line of allocation logic is written against it —
  exactly the sequencing `FeatureVector`'s freeze modeled for Milestone 4
  itself.
- `regime_id`'s explicit non-portability across models (documented in the
  Standards doc: state `2` from one trained model isn't state `2` from
  another) heads off a specific, easy-to-make mistake — comparing regime
  labels across a retrain without checking `model_version` first — before
  any consumer exists to make it.
- Pairing `model_version` and `feature_pipeline_version` on every single
  `RegimeState` (not just on the model artifact's metadata) means a
  consumer never has to cross-reference a separate file to know what
  produced a given call — the traceability travels with the object, the
  same design choice [ADR-005](ADR-005-FeatureVector-Provenance.md) made
  for `FeatureVector.provenance`.
- Trade-off, accepted deliberately: `RegimeState` is deliberately lean —
  no raw feature values, no model internals, no confidence intervals
  beyond the posterior itself. A consumer that needs more must get it
  added to this contract explicitly (new ADR) rather than reaching past
  it — narrower is easier to keep frozen than broad.

## Alternatives Considered

- **Don't freeze a contract yet; let `RegimeService`'s return type settle
  once Milestone 5 exists and knows what it actually needs** — rejected
  for the same reason ADR-004 rejected the equivalent argument for
  `FeatureVector`: "settle later" means settling after a real consumer
  already depends on the unstated shape, which is the expensive time to
  discover it needs to change.
- **Return the raw posterior vector and let each consumer compute its own
  `regime_id`/`confidence`** — rejected: this pushes the "which state is
  most likely, and how sure are we" computation to every consumer
  independently, exactly the duplicated-logic failure mode this
  platform's contracts exist to prevent (see
  [ADR-003](ADR-003-Feature-Engineering.md)'s equivalent reasoning for why
  `FeaturePipeline` exists at all). `regime_probabilities` is still
  available in `metadata` for a consumer that genuinely needs the full
  distribution, but `regime_id`/`confidence` are computed once, in one
  place, the same way every time.
