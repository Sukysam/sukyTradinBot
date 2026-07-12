# Standard — RegimeState Contract

Governs `hmm.models.RegimeState`, the single output type
`hmm.service.RegimeService.infer`/`infer_series` produce and every current
and future consumer (Strategy Engine, backtesting, risk) is expected to
read. See
[Architecture/ADR/ADR-006-RegimeState-Contract.md](../Architecture/ADR/ADR-006-RegimeState-Contract.md)
for why this type exists and was frozen ahead of any real consumer, and
[Architecture/ADR/ADR-007-HMM-Design.md](../Architecture/ADR/ADR-007-HMM-Design.md)
for the modeling decisions behind what produces it. This document is the
binding contract for anyone implementing a new consumer of regime calls.

## Why this exists

Milestone 4's mandate was to treat the HMM as an independent machine
learning service: it takes a `FeatureVector`, it returns a `RegimeState`,
nothing else. That boundary only holds if `RegimeState` itself is a
stable, documented contract — the same reasoning
[Standards/FeatureVector Contract.md](FeatureVector%20Contract.md)
established for features, applied one layer downstream. A consumer that
reaches into `RegimeService` internals (the fitted `hmmlearn.hmm.
GaussianHMM`, the normalizer, raw posterior arrays) instead of reading
`RegimeState` recreates exactly the tight coupling this milestone exists
to prevent.

## Scope

Applies to `hmm.models.RegimeState` and `hmm.service.RegimeService.infer`/
`infer_series`. Does **not** cover `hmm` package internals (`TrainedModel`,
`ModelMetadata`, the normalizer, the trainer/selector) — those are
implementation details behind the `RegimeService` boundary, free to change
without a version bump as long as `RegimeState` itself doesn't change; see
[ADR-007](../Architecture/ADR/ADR-007-HMM-Design.md)'s "freeze interfaces,
not implementation" framing.

## Required fields

| Field | Type | Guarantee |
|---|---|---|
| `timestamp` | `datetime` | Timezone-aware, normalized to UTC (enforced at construction). Exactly the input `FeatureVector`'s `timestamp` this regime call is *about* — the bar's market time, not when inference ran. |
| `symbol` | `str` | The symbol this regime call is for. Never empty. |
| `regime_id` | `int` | The filtered MAP state estimate — `argmax` of `P(S_t \| X_{1:t})`, the causal forward-algorithm posterior. `>= 0`. Not stable across retraining: state `2` from one trained model is not comparable to state `2` from another — always pair `regime_id` with `model_version` when comparing across models. |
| `confidence` | `float` | `P(S_t = regime_id \| X_{1:t})` — the posterior probability of `regime_id` itself. In `[0, 1]`. |
| `transition_probability` | `float` | `P(S_{t+1} = regime_id \| S_t = regime_id)` — the model's own transition-matrix self-probability for the *current* regime, i.e. how "sticky" it's expected to be. This is **not** a forecast of what regime comes next; a low value means the current regime is expected to be short-lived, not that a specific other regime is coming. In `[0, 1]`. |
| `model_version` | `str` | The trained model artifact's version that produced this call — see `hmm.models.ModelMetadata.model_version`. |
| `feature_pipeline_version` | `str` | Copied from the input `FeatureVector.provenance.pipeline_version` — links a regime call back to which `FeatureVector` contract version produced its input, the same traceability `Provenance` gives features themselves (see [ADR-005](../Architecture/ADR/ADR-005-FeatureVector-Provenance.md)). |
| `metadata` | `Mapping[str, Any]` | See Metadata schema below. |

`RegimeState` is an immutable (`frozen=True`) dataclass. Consumers must
never mutate an instance in place.

## Metadata schema

Keys guaranteed present in every `RegimeState.metadata` produced by
`RegimeService`:

| Key | Type | Meaning |
|---|---|---|
| `regime_probabilities` | `tuple[float, ...]` | The full filtered posterior, `P(S_t = i \| X_{1:t})` for every state `i`, in state-index order. `len(regime_probabilities) == n_states`; `regime_probabilities[regime_id] == confidence`. Sums to `1.0`. Present so a consumer that wants soft allocation (not just the MAP argmax) doesn't need to reconstruct it from `hmmlearn` internals it never has access to. |
| `n_states` | `int` | The model's total state count — the length of `regime_probabilities`, surfaced directly so a consumer doesn't have to `len()` it. |

**Policy**: this set may only grow, following the same additive-only rule
as [FeatureVector's metadata schema](FeatureVector%20Contract.md#metadata-schema).
Consumers must tolerate unknown keys.

## Model and feature versioning together

`model_version` and `feature_pipeline_version` are recorded *together* on
purpose — a regime call's meaning depends on both what model produced it
*and* what the input features meant at the time. If either changes
independently (a retrained model, or a `FeatureVector` contract bump),
comparing `RegimeState`s across that boundary without accounting for it
is a modeling error, not a data error: `regime_id=2, model_version="v1"`
and `regime_id=2, model_version="v2"` are not the same regime unless
proven otherwise. `RegimeService.infer`/`infer_series` additionally
refuse to run at all (`ContractViolationError`) if a `FeatureVector`'s
`provenance.feature_versions` has drifted from what the loaded model was
trained on — see [ADR-007](../Architecture/ADR/ADR-007-HMM-Design.md) —
so this failure mode is caught before a `RegimeState` is even produced,
not left for a downstream consumer to notice.

## Backward compatibility expectations

Follows the same allowed/requires-a-version-bump/never-permitted
structure as
[FeatureVector Contract.md](FeatureVector%20Contract.md#backward-compatibility-expectations),
applied to `RegimeState`:

**Allowed without a contract change:**
- Adding a new `metadata` key.
- Changing anything about `hmm` package internals (trainer, selector,
  normalizer, persistence format) that doesn't change `RegimeState`'s
  fields or their meaning — this is the entire point of freezing the
  interface separately from the implementation.

**Requires a new ADR and a coordinated update across every consumer:**
- Renaming, removing, or changing the type of any required field.
- Changing what `timestamp` refers to.
- Changing `transition_probability`'s definition (e.g. from "self-
  transition probability" to "probability of the most likely next
  state").
- Removing or repurposing a `metadata` key listed above.

**Never permitted, at any version**: silently changing an existing
field's meaning while keeping its name and type identical — the same
"fail loudly, never silently" principle
[00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md) applies everywhere else.

## Enforcement

- `tests/hmm/test_models.py` enforces `RegimeState`'s construction
  invariants: frozen dataclass, tz-aware UTC timestamp, non-empty symbol,
  `regime_id >= 0`, `confidence`/`transition_probability` in `[0, 1]`.
- `tests/hmm/test_service.py` enforces that `RegimeService.infer`/
  `infer_series` only ever produce `RegimeState`s satisfying this
  contract, including the `metadata` schema.
- **Known gap**, matching FeatureVector's own: there is no automated
  check that a `RegimeState`-shape change is accompanied by a new ADR.
  Code review against this document is the enforcement mechanism today.

## Ownership

Build and maintain: [Quant Researcher](../04_QUANT_RESEARCHER.md), who
owns `src/hmm/` (see
[ADR-006](../Architecture/ADR/ADR-006-RegimeState-Contract.md) and
[ADR-007](../Architecture/ADR/ADR-007-HMM-Design.md)). Binding on every
role that builds a `RegimeState` consumer: Strategy Engine
([07 Signal Orchestrator](../07_SIGNAL_ORCHESTRATOR.md), Milestone 5),
backtesting ([04 Quant Researcher](../04_QUANT_RESEARCHER.md), Milestone
8), and risk ([08 Risk Manager](../08_RISK_MANAGER.md)) if it comes to
depend on regime state directly. A consumer that needs a capability this
contract doesn't provide raises it against this document — it doesn't
reach into `RegimeService` internals to work around it.
