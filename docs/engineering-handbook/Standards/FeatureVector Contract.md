# Standard — FeatureVector Contract

Governs `features.feature_vector.FeatureVector`, the single output type
`features.pipeline.FeaturePipeline` produces and every current and future
consumer (HMM, backtesting, adaptive learning, NLP, risk) is expected to
read. See
[Architecture/ADR/ADR-003-Feature-Engineering.md](../Architecture/ADR/ADR-003-Feature-Engineering.md)
for why this type exists at all,
[Architecture/ADR/ADR-004-FeatureVector-Contract-Freeze.md](../Architecture/ADR/ADR-004-FeatureVector-Contract-Freeze.md)
for why it was frozen as a stable interface ahead of Milestone 4, and
[Architecture/ADR/ADR-005-FeatureVector-Provenance.md](../Architecture/ADR/ADR-005-FeatureVector-Provenance.md)
for the `provenance` field and the resulting v1 → v2 bump. This document
is the binding contract for anyone implementing a new feature, extending
the pipeline, or building a new consumer.

## Why this exists

Milestone 3's entire purpose was to give every future consumer one shared
contract instead of each growing its own feature-reading logic. That
guarantee only holds if the contract itself doesn't silently drift once
consumers start depending on it — a field that quietly changes meaning
between Milestone 4 and Milestone 9 is exactly the kind of defect that
looks like a data bug in a downstream model and takes far longer to
diagnose than a version mismatch would. This document exists so "silently
drift" isn't an option: every change to `FeatureVector` is either
compatible under the rules below, or it's a new version with an ADR.

## Scope

Applies to `features.feature_vector.FeatureVector`,
`features.pipeline.FeaturePipeline.compute`/`compute_series`, and
`config/feature_manifest.yaml` (the per-feature companion metadata). Does
**not** freeze the *set* of registered features — adding a new feature to
the registry is routine, ongoing work (see Backward compatibility
expectations below), not a contract change.

## Required fields

| Field | Type | Guarantee |
|---|---|---|
| `timestamp` | `datetime` | Timezone-aware, normalized to UTC (enforced at construction — a naive or non-UTC timestamp raises `ValueError`). Exactly the corresponding input bar's timestamp after cleaning/deduplication; ascending across one `compute_series` call. |
| `symbol` | `str` | The symbol the input bars belonged to. Never empty. |
| `feature_values` | `tuple[float, ...]` | Parallel to `feature_names` — see Feature ordering guarantees. |
| `feature_names` | `tuple[str, ...]` | Same length as `feature_values` (enforced at construction). Every name is either every currently-registered feature (full-registry case) or exactly the subset passed via `feature_names=` (explicit-subset case). |
| `metadata` | `Mapping[str, Any]` | See Metadata schema below. |
| `quality_flags` | `Mapping[str, bool]` | Keys are a subset of `feature_names` (enforced at construction — an unknown key raises `ValueError`). A name absent from `quality_flags` is implicitly clean (`False`) — flags are opt-in, never opt-out. |
| `provenance` | `Provenance` | Where this vector came from — see Provenance schema below. |

`FeatureVector` is an immutable (`frozen=True`) dataclass. Consumers must
never attempt to mutate an instance in place — construct a new one (e.g.
via `dataclasses.replace`) if a derived value is needed.

Prefer `.as_dict()` and `.get(name)` over indexing `feature_values`
directly — see Feature ordering guarantees for why.

## Metadata schema

Keys guaranteed present in every `FeatureVector.metadata` produced by
`FeaturePipeline` under pipeline version `"2"`:

| Key | Type | Meaning |
|---|---|---|
| `n_bars_used` | `int` | Total bars in the cleaned input this vector's `FeaturePipeline` run was computed against — constant across every vector from one `compute_series` call, not a per-feature lookback count. |

As of `PIPELINE_VERSION` `"2"`, `pipeline_version` and `source` moved out
of `metadata` and into `provenance` (see Provenance schema below and
[ADR-005](../Architecture/ADR/ADR-005-FeatureVector-Provenance.md)) —
`metadata` no longer duplicates them.

**Policy**: this set may only grow. A future pipeline version may add new
metadata keys but must never remove or repurpose an existing key's
meaning within the same `PIPELINE_VERSION`. Consumers must tolerate
unknown keys — never assert `set(metadata.keys()) == {...}` — and must
treat any key not listed above as optional/informational, not load-
bearing, until this document is updated to name it explicitly.

## Provenance schema

Fields guaranteed present on every `FeatureVector.provenance` (a
`Provenance` instance) produced by `FeaturePipeline` under pipeline
version `"2"`:

| Field | Type | Meaning |
|---|---|---|
| `pipeline_version` | `str` | The `PIPELINE_VERSION` that produced this vector — the canonical home for this information (no longer duplicated in `metadata` or a standalone `FeatureVector.version` field). |
| `manifest_version` | `str` | `manifest.MANIFEST_SCHEMA_VERSION` at computation time — the manifest *file's* schema version, not a content hash. The manifest's actual content at any point in time is fully reconstructable from `feature_versions` below plus checked-in git history. |
| `feature_versions` | `Mapping[str, int]` | `{feature_name: FeatureSpec.version}` for exactly the features in this vector — validated at construction to cover exactly `feature_names`, no more, no less. This is what lets a consumer confirm two vectors (e.g. one from training, one from live inference) were computed by identical feature definitions, not just identically-named features. |
| `generated_at` | `datetime` | Timezone-aware UTC wall-clock time the vector was computed (enforced at construction, same rule as `timestamp`) — distinct from `timestamp`, which is the bar's market time. Every vector from one `compute_series` call shares the same `generated_at` (one clock read per batch, not per vector). |
| `source_dataset` | `str` | Caller-supplied via `compute(..., source_dataset=...)`/`compute_series(..., source_dataset=...)`; defaults to `"unspecified"`. A dataset identifier or cache key — even a loose, informal one is enough to trace a vector back to what was replayed to produce it. Free-form today, not a closed enum. |

`Provenance` is itself an immutable (`frozen=True`) dataclass, constructed
fresh only by `FeaturePipeline` — consumers read it, they don't construct
or mutate it.

## Feature ordering guarantees

- **Full-registry case** (`feature_names` not passed to
  `compute`/`compute_series`): `feature_names`/`feature_values` are
  ordered alphabetically by feature name — this follows from
  `FeatureRegistry.all()`'s own contract (sorted iteration), not
  something `FeaturePipeline` does independently.
- **Explicit-subset case** (`feature_names` passed): the returned
  `FeatureVector.feature_names` preserves exactly the order the caller
  supplied — the pipeline does not re-sort a caller-provided list.
- **Consumers that persist or index features by position** (e.g. a fixed-
  column training matrix, a serialized numpy array with an assumed
  schema) **must pass an explicit `feature_names` list**, not rely on the
  full-registry's alphabetical order staying stable as the registry
  grows — a new feature registered earlier in the alphabet than an
  existing one shifts every subsequent index. This is the recommended
  pattern for any consumer that cares about positional stability across
  registry growth, and it sidesteps the ordering question entirely.

## Versioning policy

Three distinct, independently-tracked version numbers exist in this
platform — do not conflate them:

1. **`pipeline.PIPELINE_VERSION`** (mirrored at
   `FeatureVector.provenance.pipeline_version`) — versions the shape and
   semantics of the `FeatureVector` contract itself (this document). Bump
   this when a change listed under "Requires a `PIPELINE_VERSION` bump"
   below lands. Currently `"2"` — see Contract history below.
2. **`FeatureSpec.version`** (per feature, visible in
   `config/feature_manifest.yaml`) — versions *one feature's own
   computation semantics*. Bump a single feature's `version` when its
   formula changes in a way that would produce different historical
   values for the same input bars (e.g. changing `atr_14`'s smoothing
   method) — the feature *name* stays the same and consumers keep reading
   `atr_14`, but the manifest's `version` field for it increments so a
   consumer diffing manifests across time can detect the semantic change.
3. **`manifest.MANIFEST_SCHEMA_VERSION`** — versions the shape of the
   manifest YAML file itself (its top-level keys), independent of both of
   the above.

A `PIPELINE_VERSION` bump and a `FeatureSpec.version` bump are
independent events — adding a feature or changing one feature's formula
does not, by itself, require bumping `PIPELINE_VERSION`; see Backward
compatibility expectations.

## Backward compatibility expectations

**Allowed without a `PIPELINE_VERSION` bump** (additive, non-breaking):

- Registering a new feature. The registry grows; a consumer using an
  explicit `feature_names` list is unaffected; a consumer reading the
  full registry gets a longer vector, which is the expected, documented
  behavior of that mode (see Feature ordering guarantees).
- Bumping an individual `FeatureSpec.version` for a formula change to
  that one feature — the contract (field names, types, ordering rules)
  hasn't changed, only that feature's own values going forward.
- Adding a new `metadata` key (per the Metadata schema policy above).
- A feature's `quality_flags` entry appearing under a previously-unseen
  condition — flags are a "may be present" contract already.

**Requires a `PIPELINE_VERSION` bump, and a corresponding ADR:**

- Renaming, removing, or changing the type of any required
  `FeatureVector` field.
- Changing what `timestamp` refers to (e.g. bar close time to bar open
  time).
- Removing a previously-registered feature name a consumer may depend on.
- Changing the alphabetical-ordering guarantee for the full-registry
  case, or the order-preservation guarantee for the explicit-subset case.
- Changing `quality_flags` semantics (e.g. from "may be suspect" to "must
  not be used downstream").
- Removing or repurposing an existing `metadata` key's meaning.

**Never permitted, at any version**: silently changing an existing
field's meaning while keeping its name and type identical. If a field's
meaning must change, that's either a new field or a `PIPELINE_VERSION`
bump with a migration note in the ADR that introduces it — a consumer
holding old assumptions must fail loudly (missing field, version
mismatch) rather than silently misinterpret new data. This is the same
"fail loudly, never silently" principle
[00_MASTER_CHARTER.md](../00_MASTER_CHARTER.md) applies everywhere else in
this system.

## Contract history

- **v1** (Milestone 3): initial contract — `timestamp`, `symbol`,
  `feature_values`, `feature_names`, `metadata`, `quality_flags`,
  `version`. `metadata` carried `pipeline_version` (duplicating the
  top-level `version` field) and a free-text `source`.
- **v2** ([ADR-005](../Architecture/ADR/ADR-005-FeatureVector-Provenance.md),
  pre-Milestone-4): added the required `provenance: Provenance` field.
  Removed the standalone `version` field and `metadata["pipeline_version"]`/
  `metadata["source"]` — all now live exclusively under `provenance`
  (`pipeline_version`, `source_dataset`). Added `provenance.
  manifest_version` and `provenance.feature_versions`, neither of which
  existed anywhere on the vector before. Landed with zero external
  consumers depending on the old shape yet — see ADR-005's Context for why
  this was the right time to make a breaking change cheaply.

## Enforcement

- `tests/features/test_feature_vector.py` enforces the required-field
  construction invariants: frozen dataclass, tz-aware UTC timestamp,
  matching `feature_values`/`feature_names` lengths, `quality_flags`
  referencing only known names.
- `tests/features/test_manifest.py::test_checked_in_manifest_is_up_to_date`
  enforces that `config/feature_manifest.yaml` — where each feature's
  `version` lives — never silently drifts from what the registry would
  regenerate.
- **Known gap**: there is currently no automated test asserting
  `PIPELINE_VERSION` itself gets bumped when a breaking change lands.
  That judgment call is the responsibility of whoever makes the change,
  reviewed against this document during code review — not yet a
  mechanically enforced check.

## Ownership

Build and maintain: [Quant Researcher](../04_QUANT_RESEARCHER.md), who
owns `src/features/` (see
[ADR-003](../Architecture/ADR/ADR-003-Feature-Engineering.md),
[ADR-004](../Architecture/ADR/ADR-004-FeatureVector-Contract-Freeze.md),
and [ADR-005](../Architecture/ADR/ADR-005-FeatureVector-Provenance.md)).
Binding on every role that builds a `FeatureVector` consumer: HMM and
backtesting ([04 Quant Researcher](../04_QUANT_RESEARCHER.md)), adaptive
learning ([05 Memory Engineer](../05_MEMORY_ENGINEER.md)), NLP
([06 NLP Engineer](../06_NLP_ENGINEER.md)), risk
([08 Risk Manager](../08_RISK_MANAGER.md)). A consumer that needs a
capability this contract doesn't provide (e.g. positional stability
without passing `feature_names`) raises it against this document — it
doesn't reach into `FeaturePipeline` internals to work around it.
