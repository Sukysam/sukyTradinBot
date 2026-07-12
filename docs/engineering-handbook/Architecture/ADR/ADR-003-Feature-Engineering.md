# ADR-003: Feature Engineering Platform

**Status**: Accepted
**Date**: 2026-07-12
**Milestone**: [3 — Feature Engineering Platform](../../../../PROJECT_STATUS.md)

## Context

Milestone 3 was inserted ahead of HMM & Regime Detection specifically so
the HMM — and every other future consumer: backtesting, adaptive
learning, SHAP explainability, NLP, risk — never computes an indicator
against raw bars itself. That only works if this milestone produces one
thing every consumer actually depends on, not a library of indicator
functions each consumer is free to call differently. `regime-trader/data/
feature_engineering.py` already implements a strictly causal subset (log
returns, rolling volatility, ADX, RSI, momentum, ATR, 252-day rolling
z-scores) — per Milestone 3's own scope, this had to extend and formalize
that existing math into a fully-tooled `src/` package, not replace it or
duplicate it under a second, drifting implementation. This record covers
the platform's structural decisions; it does not implement any HMM or
strategy logic, which remains Milestone 4's scope.

---

## Decision 1: `FeatureVector` is the one shape every consumer reads

**Status**: Accepted

### Context

Without a canonical output type, "every future consumer uses the same
pipeline" is just a stated intention — nothing stops a second consumer
from reading `FeaturePipeline`'s internal DataFrame directly, coupling
itself to column order and dtype choices that were never meant to be a
public contract.

### Decision

`features.feature_vector.FeatureVector` is a frozen dataclass —
`timestamp`, `symbol`, `feature_values: tuple[float, ...]`,
`feature_names: tuple[str, ...]`, `metadata`, `quality_flags`, `version`
— validated at construction (UTC-aware timestamp, `feature_values`/
`feature_names` length match, no unknown `quality_flags` keys). It is the
only type `FeaturePipeline.compute`/`compute_series` return; nothing
downstream is handed a raw DataFrame from this package.

### Consequences

- A consumer that only wants `atr_14` and `rsi_14` still gets the same
  `FeatureVector` shape as one reading the full registry, just with
  `feature_names=("atr_14", "rsi_14")` — see `compute`'s `feature_names`
  parameter. Nothing about the contract changes with subset size.
- `quality_flags` travels with the vector instead of being a side-channel
  a caller has to separately reconstruct — a caller running in `strict`
  mode (see Decision 2's sibling, `compute(..., strict=True)`) can refuse
  to act on a partially-warmed-up vector using only fields already on the
  object it was handed.
- Trade-off: `feature_values`/`feature_names` as parallel tuples (not a
  `dict[str, float]`) trades a slightly less ergonomic call site
  (`vec.get("atr_14")` instead of `vec.features["atr_14"]`) for a
  guaranteed-immutable, hashable value object — accepted because
  `FeatureVector` is meant to be freely passed across process/consumer
  boundaries (HMM training, backtesting replay) without risk of a
  downstream consumer mutating a shared feature dict out from under
  another one.

### Alternatives Considered

- **Return the internal feature-matrix DataFrame directly, like
  `regime-trader/data/feature_engineering.py`'s existing
  `build_feature_matrix`** — rejected: this is precisely the shape this
  milestone exists to move every consumer off of. `feature_engineering.py`
  itself is left untouched (see Decision 3) rather than migrated in this
  milestone, since retargeting `regime-trader/`'s own callers is out of
  Milestone 3's stated scope ("do not implement HMM or strategy logic
  yet").

---

## Decision 2: Leakage protection is enforced at registration, not by convention

**Status**: Accepted

### Context

[Standards/Anti-Lookahead Checklist.md](../../Standards/Anti-Lookahead%20Checklist.md)
already documents the discipline every feature must follow. A checklist a
human re-reads per feature doesn't scale to 39 features across 7 modules,
and doesn't stop a future feature from being added without anyone
re-reading it at all.

### Decision

Every feature is registered via the `@feature(...)` decorator into a
single `FeatureRegistry` (`DEFAULT_REGISTRY`). `FeatureSpec.__post_init__`
raises `ValueError` if `uses_future_data=True` is ever passed — there is
no opt-out — and a generic, registry-driven test
(`tests/features/test_no_lookahead_all_features.py::test_feature_is_causal`,
parametrized over every registered feature) computes each feature twice
against a 150-bar fixture, once unperturbed and once with only the *last*
bar's price/volume perturbed, and asserts every row except the last is
byte-identical between the two runs. A feature that peeks ahead fails this
test automatically the moment it's registered — no per-feature test has
to be hand-written to catch it.

### Consequences

- Adding feature #40 gets the same leakage test as feature #1 for free,
  simply by using `@feature(...)` — the test file itself never grows.
- `test_registry_is_not_accidentally_empty` (`assert
  len(DEFAULT_REGISTRY) >= 30`) exists specifically so a broken import
  (e.g. one category module silently failing to register) fails loudly
  as a missing-coverage bug instead of the causality test suite silently
  passing over zero features.
- Trade-off: this only catches *look-ahead*, not every possible
  correctness bug (a feature can be perfectly causal and still wrong) —
  accepted, since correctness is covered separately by each category
  module's own value-level tests (`tests/features/test_price.py`,
  `test_volatility.py`, etc.), and conflating the two would make a
  causality failure harder to distinguish from a value bug.

### Alternatives Considered

- **A lint rule or static-analysis check for look-ahead patterns (e.g.
  banning `.shift(-1)`)** — rejected: look-ahead is a data-flow property,
  not a syntactic one (a feature can leak future data through far less
  obvious means, e.g. a global rolling `.mean()` computed once over the
  whole series before windowing). The perturbation test catches the
  actual property that matters — does changing bar N ever change row
  N-1's output — regardless of how the leak would have been written.

---

## Decision 3: The pipeline reuses `market_data.validation` directly; it does not re-clean bars

**Status**: Accepted

### Context

`market_data.validation` (Milestone 2) already implements bar-level
validation, deduplication, gap detection, and split adjustment, tested to
97%+ coverage. Feature computation needs all of that done *before* any
feature touches a bar — reimplementing it here would create a second,
inevitably-diverging copy of logic Milestone 2 already owns.

### Decision

`FeaturePipeline._prepare` calls `market_data.validation.validate_bars`,
`deduplicate_bars`, and `apply_split_adjustment` directly — `features`
depends on `market_data.models`/`market_data.validation` at import time,
never the reverse. `features`'s own `validation.py` handles only what is
new at this layer: feature *output* shape checking and NaN-derived
quality-flag computation. Missing bars are surfaced via
`PipelineDiagnostics` but are not fatal by default — real market data has
minor gaps (trading halts, thin liquidity) a hard failure would make this
pipeline unusable for.

### Consequences

- The `features` extras group depends on `pandas`/`numpy`/`ta` but not
  `pyarrow`/`duckdb`/`alpaca-py` — `market_data.models` and `market_data.
  validation` alone don't need them (see `pyproject.toml`'s `features`
  extras group comment), so installing `features` alone stays lean.
- A bug fix to gap detection or split adjustment lands once, in
  `market_data`, and every consumer (storage, replay, and now features)
  gets it — verified directly by this milestone's own corporate-action
  test (`test_split_adjustment_removes_the_artificial_price_jump`), which
  exercises `market_data.validation.apply_split_adjustment` through the
  feature pipeline rather than re-testing split math independently.
- Trade-off: `features` is now coupled to `market_data`'s bar model and
  validation report shape — accepted, since `market_data` is exactly the
  shared foundation Milestone 2 was built to be, and the alternative
  (duplicating bar cleaning here) is the actual anti-goal.

### Alternatives Considered

- **Reindex bars to a full expected-timestamp range and forward-fill
  gaps before feature computation** — rejected for this milestone: it
  would silently manufacture bars that never traded, which every
  causality/quality-flag mechanism here is built to make visible, not
  hide. Gaps stay gaps; `PipelineDiagnostics.missing_bar_count` and each
  feature's own `NaN`-on-insufficient-history behavior are the signal a
  caller acts on instead.

---

## Decision 4: Confirmed, lagged reporting for market-structure signals

**Status**: Accepted

### Context

A "swing high" is conventionally defined by comparing a candidate bar to
`k` bars *after* it as well as before — the standard definition is
inherently non-causal. Computing it naively at bar `t` using data through
`t+k` would be exactly the look-ahead Decision 2's test suite exists to
catch.

### Decision

`market_structure.py`'s `swing_high_confirmed`/`swing_low_confirmed`
report a signal *about* bar `t - k` (`_SWING_CONFIRM_BARS = 5`), not
about the current bar `t` — the confirmation window `[t-2k, t]` is
entirely `<= t`, so the feature is exactly as causal as any other, it
just describes something `k` bars in the past by the time it's reported.

### Consequences

- A consumer reading `swing_high_confirmed` at time `t` is reading "a
  swing high was confirmed at `t-5`," not "there is a swing high right
  now" — documented explicitly in the feature's description/manifest
  entry so this lag is a declared property of the feature, not a
  surprise a consumer discovers by backtesting against it.
- The same perturbation test from Decision 2 passes for these features
  with no special-casing, which is itself a confirmation the lag is
  sufficient — if it weren't, perturbing the last bar would still change
  an earlier row's swing-point flag.

### Alternatives Considered

- **Report an unconfirmed/provisional swing point at `t` that can later
  be retracted** — rejected: a value that can change after the fact for
  a timestamp already handed to a consumer violates the same causality
  guarantee this whole platform exists to provide, just moved from
  "look-ahead in computation" to "look-ahead in mutation."

---

## Decision 5: A generated-but-checked-in Feature Manifest

**Status**: Accepted

### Context

Milestone 3 asked for a machine-readable feature catalog — name,
category, version, lookback, dtype, description, `uses_future_data`,
`depends_on` — as documentation/configuration other tooling (and humans)
can read without importing Python. Hand-maintaining that file separately
from the `@feature(...)` declarations it describes would let it drift the
first time a feature's `lookback` changed and the manifest didn't.

### Decision

`features.manifest.build_manifest`/`write_manifest` generate
`config/feature_manifest.yaml` directly from `DEFAULT_REGISTRY` — the
single source of truth stays the `@feature(...)` decorators in
`src/features/*.py`. The generated file is checked into git (a deliberate
`.gitignore` negation, `!config/feature_manifest.yaml`, against the
otherwise-ignored `config/*.yaml` pattern), and
`test_checked_in_manifest_is_up_to_date` fails the moment the checked-in
file and a fresh regeneration diverge.

### Consequences

- A change to any feature's metadata (this milestone's own `adx_14`
  `lookback` correction is a real example — see the Verification note
  below) is caught by the test suite the moment the manifest isn't
  regenerated to match, rather than silently shipping a stale catalog.
- External tooling (or a human) can read `config/feature_manifest.yaml`
  directly — no Python import, no running code — to answer "what features
  exist, what do they depend on, what's their lookback" for any consumer
  that isn't itself Python.
- Trade-off: every metadata change requires an explicit regeneration step
  before committing — accepted, since the alternative (generating it at
  import time / on every pipeline run) would make `config/` no longer a
  stable, diffable, checked-in artifact.

### Alternatives Considered

- **Hand-write and hand-maintain the manifest YAML** — rejected: exactly
  the drift risk described in Context, and this milestone caught its own
  potential instance of that drift (the `adx_14` lookback fix) purely
  because the freshness test exists.

---

## Decision 6: Deferred out of this milestone's scope

**Status**: Accepted

### Context

Two items named in Milestone 3's original feature list — the "Regime"
category's cross-symbol "correlation changes" feature, and wiring
`FeaturePipeline` into `regime-trader/main.py` as the live/backtest
feature source — depend on things this milestone deliberately does not
build.

### Decision

`regime.py`'s module docstring documents, rather than silently omits,
that a cross-symbol correlation-shift feature is out of scope here: every
feature in this registry is a pure function of one symbol's own bar
history (`compute(df) -> pd.Series`), and a genuinely cross-symbol feature
needs either a different `FeatureSpec.compute` signature or a
multi-symbol orchestration layer above `FeaturePipeline` — a real design
decision, not a follow-up detail, deferred to whichever future milestone
first needs a cross-symbol signal (candidate: Milestone 11, Signal
Orchestration). Similarly, `regime-trader/main.py` is not modified in
this milestone — per the milestone's own instruction ("do not implement
HMM or strategy logic yet"), there is no consumer ready to be pointed at
this pipeline yet; wiring it in now would mean `main.py` importing a
pipeline nothing in `regime-trader/` calls, an unused integration point
rather than a real one.

### Consequences

- `liquidity_proxy_20` (Amihud illiquidity) and `volatility_clustering_20`
  ship in the `Regime` category as the two genuinely single-symbol
  regime-adjacent features Milestone 3 could deliver honestly; the
  category is not yet "complete" against the original spec, and isn't
  claimed to be.
- Milestone 4 (HMM & Regime Detection) is the first real consumer; its
  own ADR is where `FeaturePipeline` actually gets wired into a call
  site, at which point `regime-trader/main.py`'s eventual migration
  becomes that milestone's decision to make, not this one's.

### Alternatives Considered

- **Build a placeholder cross-symbol feature now (e.g. hardcoded to a
  fixed reference symbol) to satisfy the original feature list literally**
  — rejected: a placeholder that doesn't generalize to "any symbol against
  any other symbol" would need to be thrown away rather than extended once
  a real multi-symbol orchestration layer exists, and would ship a feature
  whose behavior depends on an arbitrary hardcoded choice nothing in this
  milestone's spec actually justifies.

---

## Verification note

Two real bugs in the third-party `ta` library were found and fixed during
this milestone's edge-case testing (`tests/features/test_edge_cases.py`,
constructed specifically to exercise `make_bars(1)`/`make_bars(2)`/gapped
histories per Milestone 3's required edge-case list): `ta.trend.
ADXIndicator.adx()` and `ta.volatility.AverageTrueRange.
average_true_range()` both raise an unguarded `IndexError` — not a
graceful `NaN` — when given fewer rows than they need internally.
Boundary-tested directly (`atr_14` needs `len(df) >= 14`; `adx_14` needs
`len(df) >= 2 * 14 = 28`, not `window + 1` as first assumed and shipped,
then corrected after a gapped-history test caught the under-guard with a
25-row input). Both features now short-circuit to an all-`NaN` `Series`
below their true minimum, matching every other feature's NaN-on-
insufficient-history contract instead of crashing the pipeline.

A real performance bug was also found and fixed, not merely measured
around: `FeaturePipeline.compute_series`'s row-construction loop was
calling `.iloc[i]` on a DataFrame per output row, which reconstructs a
full pandas `Series` on every call — this dominated wall-clock time far
more than any single feature's own cost (9.46s of a 10.5s total on a
21-trading-day, 1-minute-bar run), including `hurst_exponent_100`, the
registry's most expensive individual feature. Replacing the per-row
`.iloc` calls with one `DataFrame.to_numpy()`/`Series.tolist()` conversion
up front cut that same run to ~0.5s (excluding Hurst) and ~3.2s (the full
39-feature registry, Hurst included) — comfortably inside Milestone 3's
stated 1-minute-bar target (<5s) in both cases; see `tests/features/
test_performance.py` for the measured numbers and
`FeaturePipeline.compute_series`'s inline comment for the mechanism.
`hurst_exponent_100` remains the single most expensive feature by a wide
margin (~2.6s standalone) and is still excluded from the platform's
recommended 1-minute-bar feature subset on conventional-use grounds (a
100-bar window covers under two trading hours at that granularity), not
because it's still a performance blocker.

All measurements and edge cases in this milestone use the deterministic
synthetic bar generator (`tests/features/conftest.py::make_bars`, seeded)
— no feature in this registry has yet been run against real historical or
live market data pulled through `market_data`'s Alpaca providers. That
remains true until a consumer (Milestone 4 onward) actually exercises the
pipeline end-to-end against `market_data`'s storage/replay layer.
