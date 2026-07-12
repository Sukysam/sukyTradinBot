# ADR-007: HMM & Regime Detection Design

**Status**: Accepted
**Date**: 2026-07-12
**Milestone**: [4 — HMM & Regime Detection](../../../../PROJECT_STATUS.md)

## Context

Milestone 4 built `src/hmm/`: a deterministic, reproducible Gaussian HMM
engine that consumes only the frozen `FeatureVector` contract (v2, with
`Provenance` — see [ADR-005](ADR-005-FeatureVector-Provenance.md)) and
produces only the frozen `RegimeState` contract (see
[ADR-006](ADR-006-RegimeState-Contract.md)). This is the first true
machine-learning component in this codebase — the platform's success
criteria for it, per its own charter, are correctness, reproducibility,
isolation, and maintainability, explicitly *not* trading performance yet.
This record covers the modeling and engineering decisions behind it, and
is explicit throughout about which of those decisions are part of the
frozen interface versus quantitative choices expected to be revisited —
"freeze interfaces, not implementation," per the guidance this milestone
was built against.

---

## Decision 1: Port the existing causal algorithms; don't reinvent them

**Status**: Accepted

### Context

`regime-trader/core/hmm_engine.py` already implements a strictly causal
Forward Algorithm (`forward_algorithm`, `ForwardFilter`) and BIC-based
model selection (`fit_with_bic_selection`) — proven, careful code that
explicitly never calls `GaussianHMM.predict_proba` (smoothed) or
`.predict`/`.decode` (Viterbi) for inference, both of which would leak
future observations into a state estimate at time `t`. Milestone 3's own
precedent ([ADR-003](ADR-003-Feature-Engineering.md)) was to extend
existing causal math into the new `src/` package rather than reimplement
it from scratch.

### Decision

`src/hmm/inference.py`'s `forward_algorithm` and `src/hmm/selector.py`'s
free-parameter counting (`_n_free_parameters`) are ported directly from
`hmm_engine.py` — same math, same causality guarantee, same restart/
local-optimum handling in `trainer.py`. `regime-trader/core/hmm_engine.py`
itself is left untouched; no consumer is re-pointed at `src/hmm/` in this
milestone (see Decision 7).

### Consequences

- The single most safety-critical property of this whole package —
  "a regime call at time `t` never depends on data after `t`" — is
  inherited from code that already had this property proven and tested,
  not re-derived under this milestone's time pressure.
- `tests/hmm/test_inference.py::test_perturbing_a_later_row_does_not_change_an_earlier_posterior`
  is the direct analog of `tests/features/test_no_lookahead_all_features.py`'s
  perturbation test, applied to the Forward Algorithm instead of a single
  feature — the same causality-proof-by-test pattern, one layer downstream.

### Alternatives Considered

- **Import `hmm_engine.py`'s functions directly instead of porting them**
  — rejected: `regime-trader/` is outside this repository's own Ruff/
  Black/MyPy/pytest tooling scope (see
  [Architecture/Known Gaps.md](../Known%20Gaps.md)'s tooling-scope note),
  and a fully-tooled package taking a hard runtime dependency on an
  untooled one would make `src/hmm/`'s own strict-MyPy/test guarantees
  meaningless the moment `hmm_engine.py` changes underneath it.

---

## Decision 2: A full-covariance `GaussianHMM` with everything quantitative left configurable

**Status**: Accepted

### Context

State count, covariance type, convergence thresholds, and initialization
strategy are all real, unsettled modeling questions — this is the first
model built against this platform's actual feature definitions, and no
amount of a priori reasoning substitutes for evaluating it against real
data. Freezing any of these now would be freezing an implementation
detail this milestone explicitly isn't supposed to freeze.

### Decision

`hmm.config.TrainingConfig` (covariance type, restarts, iteration count,
tolerance, random seed) and `hmm.config.SelectionConfig` (candidate state
counts, BIC/AIC criterion) are the *only* place these choices live —
every one is a named, overridable default, never a hardcoded constant
inside `trainer.py`/`selector.py`. The default covariance type is
`"full"`, matching `hmm_engine.py`'s existing choice, and the default
candidate range is `(3, 4, 5, 6, 7)`, also matching it — inherited
defaults, not re-derived, but explicitly not frozen the way `RegimeState`
is.

### Consequences

- Re-evaluating covariance type (`"diag"` vs `"full"`) or the candidate
  state range later is a config change, not a code change or a new ADR —
  exactly the "don't over-freeze" boundary this record exists to be
  explicit about.
- `TrainingConfig`/`SelectionConfig` are validated at construction (e.g.
  `n_init >= 1`, `candidate_states` non-empty) so a misconfiguration
  fails immediately at the call site, not partway through an expensive
  fit.

### Alternatives Considered

- **Freeze a single default configuration as "the" model spec, changeable
  only via a new ADR** — rejected: conflates a genuinely frozen interface
  (`RegimeState`) with a set of hyperparameters this milestone's own
  charter says should remain fluid until evaluated against real
  performance.

---

## Decision 3: Deterministic z-score normalization; missing values are dropped, never imputed

**Status**: Accepted

### Context

Work Package 3 named "missing value handling" as an explicit
responsibility. A rolling technical indicator can legitimately flag-and-
NaN a single value during its warmup window (see
[Standards/FeatureVector Contract.md](../../Standards/FeatureVector%20Contract.md)) —
but a regime call has no equivalent partial-credit answer: it needs every
required feature present for the row it's inferring over.

### Decision

`hmm.normalizer.ZScoreNormalizer` fits `(x - mean) / std` per feature,
flooring `std` at `1e-12` so a constant feature transforms to `0.0`
rather than `inf`/`nan`. `hmm.normalizer.drop_incomplete_rows` removes any
row with at least one NaN *before* fitting or training — training data
with missing features is thinned, never mean-filled or forward-filled.
At inference time, `RegimeService.infer`/`infer_series` raise
`InsufficientDataError` outright if any row in the supplied history has a
missing required feature, rather than silently producing a regime call
from a partially-observed input.

### Consequences

- A model trained on a window with warmup NaNs (the normal case — the
  first `lookback`-many rows of any `FeaturePipeline` output are flagged)
  trains cleanly on the rows that are actually complete, verified by
  `tests/hmm/test_quantitative.py::TestMissingValues`.
- "Fail loudly" extends to inference: a caller that accidentally includes
  a warmup-flagged vector in a live inference call gets an immediate,
  specific exception, not a regime call quietly computed from garbage.
- Trade-off, accepted: dropping incomplete rows shrinks the effective
  training window without any signal to the caller beyond
  `ModelMetadata.n_samples` being smaller than `len(history)` — no
  separate "here's what got dropped and why" diagnostic exists yet,
  matching `FeaturePipeline.compute_series`'s own choice not to expose
  more than `PipelineDiagnostics`' aggregate counts.

### Alternatives Considered

- **Impute missing values (mean-fill or forward-fill) so no training row
  is ever discarded** — rejected outright: this is exactly the kind of
  fabricated-but-plausible-looking value
  [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md) principle #2 ("fail
  loudly, never silently") exists to prevent. A regime model trained
  partly on invented data is a correctness bug wearing a robustness
  costume.

---

## Decision 4: Both BIC and AIC are always computed; the criterion is a config choice

**Status**: Accepted

### Context

Work Package 5 asked for configurable BIC/AIC selection. Computing only
whichever criterion is currently configured would mean switching criteria
later requires retraining, and would make it impossible to sanity-check
whether the two criteria agree on a given dataset.

### Decision

`hmm.selector.select` fits every candidate state count exactly once and
computes *both* `bic` and `aic` for each successful fit
(`SelectionResult.bic_by_candidate`/`aic_by_candidate`), then picks the
winner using whichever criterion `SelectionConfig.criterion` names. Both
scores are recorded in `ModelMetadata` regardless of which one drove the
decision.

### Consequences

- Switching the selection criterion for a future retrain is a one-line
  config change; comparing what BIC vs. AIC would each have chosen for an
  already-trained model requires no retraining at all — both are already
  in `metadata.json`.
- `tests/hmm/test_selector.py::TestCriteria::test_bic_penalizes_more_than_aic_for_same_model`
  documents the actual relationship between the two formulas as a test,
  not just a comment.

### Alternatives Considered

- **Only compute the configured criterion** — rejected as the cheaper-
  looking option that isn't actually cheaper: refitting every candidate
  again just to compare criteria post hoc costs far more than the second
  scalar computation `bic`/`aic` each add per already-fitted candidate.

---

## Decision 5: Filesystem persistence, versioned per symbol, three files

**Status**: Accepted

### Context

Work Package 7 named the exact artifact shape: `model.pkl`,
`normalizer.pkl`, `metadata.json`. A regime model is expected to be fit
per ticker (see `regime-trader/main.py`'s `ModelStore.get_model(ticker)`
Protocol and Known Gaps item 3), and retraining must never silently
clobber a prior artifact something else might still be reading.

### Decision

`hmm.persistence.save`/`load` write/read exactly those three files under
`{base_dir}/{symbol}/{model_version}/`. `model.pkl` pickles the fitted
`GaussianHMM` directly; `normalizer.pkl` pickles `ZScoreNormalizer.
to_dict()`'s plain JSON-serializable output, not the class instance
itself, so the persisted format doesn't depend on that class's Python
implementation surviving unchanged; `metadata.json` is written via
`common.io.atomic_write_json`, the same crash-safe primitive every other
durable state file in this repository already uses. `save` refuses to
write a `trained_model`/`metadata` pair whose `n_states` disagree.

### Consequences

- `RegimeService.load(base_dir, symbol, model_version)` is a complete,
  self-contained way to reconstruct a usable model from disk — verified
  end to end by `tests/hmm/test_service.py::TestSaveLoad::
  test_full_train_save_load_infer_cycle` and, against real
  `FeaturePipeline` output rather than synthetic vectors, by
  `tests/hmm/test_service_integration.py`.
- Two versions of the same symbol's model can coexist on disk
  indefinitely — retraining is additive, matching
  [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md) invariant #7's
  "additive and reversible, never destructive" principle applied to a new
  kind of state file.
- `persistence.load` raises `PersistenceError` (never returns a partially
  loaded model) if any of the three files is missing or fails to
  deserialize — verified by `tests/hmm/test_persistence.py::TestLoadErrors`.

### Alternatives Considered

- **A single combined pickle of the whole `RegimeService` state** —
  rejected: three separate files with one well-defined role each
  (model, normalizer, metadata) means `metadata.json` alone is human-
  and tool-readable without unpickling anything, the same reasoning
  [ADR-003](ADR-003-Feature-Engineering.md) Decision 5 applied to
  generating a manifest instead of hand-maintaining one.

---

## Decision 6: Feature-version drift is a hard error at inference time

**Status**: Accepted

### Context

[ADR-005](ADR-005-FeatureVector-Provenance.md) added `Provenance.
feature_versions` to `FeatureVector` specifically so a consumer could
detect when a feature's underlying formula had changed since some
reference point. Milestone 4 is the first real chance to use that
capability for something concrete: confirming that training and live
inference are reading features defined the same way.

### Decision

`ModelMetadata.feature_versions` snapshots `{feature_name:
FeatureSpec.version}` as of the *last* vector in the training window.
`RegimeService.infer`/`infer_series` compare every inference vector's
`provenance.feature_versions` against that snapshot and raise
`ContractViolationError` on any mismatch — inference simply refuses to
run against a model trained on different feature semantics than what's
being fed to it now.

### Consequences

- This is the direct, concrete payoff of building `Provenance` before
  Milestone 4 started, not a hypothetical future benefit — see
  `tests/hmm/test_service.py::TestInfer::test_infer_rejects_feature_version_drift`.
- A future feature-formula change (e.g. `atr_14`'s smoothing method) that
  isn't accompanied by retraining every model depending on it fails
  loudly the next time inference runs, instead of silently producing a
  regime call from a feature stream that quietly stopped meaning what the
  model was trained to expect.
- Trade-off, accepted: this snapshots feature versions only from the
  *last* row of the training window, not the whole window — if a
  feature's version changed mid-training-window, that's not separately
  detected. Noted as a simplification, not solved here; a training window
  spanning a live feature-formula change is an edge case this milestone
  didn't build dedicated handling for.

### Alternatives Considered

- **Log a warning on drift instead of raising** — rejected: this is
  exactly the class of defect [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md)
  principle #1 calls "the single most dangerous class of defect this
  codebase can contain" when applied to look-ahead; a silently-drifted
  feature definition feeding a live regime call is the same shape of
  danger — it doesn't crash, it just quietly produces a wrong answer.

---

## Decision 7: Deliberately deferred out of this milestone's scope

**Status**: Accepted

### Context

Several things named or implied by Milestone 4's brief depend on a real
consumer or real production constraints this milestone doesn't have yet.

### Decision

- **Incremental, O(1)-per-call live inference** (`hmm_engine.py`'s
  `ForwardFilter`) is not ported. `RegimeService.infer`/`infer_series`
  re-run the batch `forward_algorithm` over the entire supplied history
  window every call, mirroring `FeaturePipeline.compute()`'s own
  recompute-over-a-window shape rather than maintaining server-side
  filter state across calls. See `inference.py`'s module docstring and
  `tests/hmm/test_performance.py`'s honest finding: ~20ms per call over a
  252-bar window, not the originally-targeted <5ms, which is only
  achievable today with a shorter live window and is the direct payoff of
  building the incremental filter once a real low-latency consumer
  exists.
- **`regime-trader/main.py`'s `ModelStore` Protocol is not satisfied.**
  That Protocol's `get_model(ticker)` returns a raw `GaussianHMM` —
  directly incompatible with this milestone's "never expose `hmmlearn`
  internals outside the package" requirement. Reconciling the two is
  explicitly left to whichever milestone first wires a real consumer to
  `src/hmm/` (candidate: Milestone 5), since it requires either changing
  `main.py`'s `Protocol` (a System Architect decision, not a Quant
  Researcher one — see [ADR-002](ADR-002-Market-Data.md) Decision 5's
  identical reasoning for `MarketDataProvider`) or building an adapter
  that wraps `RegimeService` behind the existing signature.
- **Cross-symbol or portfolio-level regime modeling** is out of scope —
  every `RegimeService` instance is trained and scoped to exactly one
  symbol, matching `FeatureVector`'s own single-symbol scope (see
  [ADR-003](ADR-003-Feature-Engineering.md) Decision 6's identical
  deferral for cross-symbol features).

### Consequences

- Milestone 5 (or whichever milestone first consumes `RegimeState`) has
  two explicit, named integration decisions waiting for it — not
  surprises discovered mid-implementation.
- This milestone's own performance numbers are honestly reported against
  what was actually built (a recompute-per-call service), not against an
  incremental filter that doesn't exist yet.

### Alternatives Considered

- **Port `ForwardFilter` now, unused, so it's "ready"** — rejected:
  speculative code with no caller and no test exercising its actual
  incremental-vs-batch equivalence is a worse starting point than clearly
  documenting the gap and building it against a real need later, per
  [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md) Definition of Done's
  rule against speculative abstraction.

---

## Verification note

A real, previously-latent bug was found and fixed during this milestone's
quantitative testing (`tests/hmm/test_quantitative.py::TestConstantSeries`,
part of the required edge-case checklist): `scipy.stats.multivariate_normal.
logpdf`, called from `inference._log_emission_matrix`, defaults to
`allow_singular=False` and raises `LinAlgError` whenever a fitted
component's covariance matrix is exactly singular — reproduced directly by
a constant-valued feature column, which collapses to a rank-deficient
sample covariance after normalization. Fixed by passing
`allow_singular=True`, which falls back to the Moore-Penrose pseudo-inverse
for the degenerate case and is a no-op for the common well-conditioned
one. The identical, unfixed exposure exists in the ported-from source,
`regime-trader/core/hmm_engine.py`'s own `_log_emission_matrix` — flagged
as a follow-up task rather than fixed in this change, since
`regime-trader/` is outside this milestone's scope and has no existing
test suite to verify the fix against.

All training, selection, inference, and persistence in this milestone's
own test suite uses either directly-constructed synthetic `FeatureVector`s
(precise control over regime structure for the quantitative checklist) or
real `FeaturePipeline` output over synthetic bars
(`tests/hmm/test_service_integration.py`) — no model in this milestone has
been trained or run against real historical or live market data. That
remains true until a real consumer (Milestone 5 onward) exercises this
package end to end against `market_data`'s storage/replay layer.
