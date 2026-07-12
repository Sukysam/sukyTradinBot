# ADR-009: Strategy Engine Design

**Status**: Accepted
**Date**: 2026-07-12
**Milestone**: [5 — Strategy Engine](../../../../PROJECT_STATUS.md)

## Context

Milestone 5 built `src/strategy/`: the first real consumer of the frozen
`RegimeState` contract, converting `RegimeState` (with `FeatureVector` as
context) into a `StrategyDecision`. Its own charter is narrow and
explicit — select a strategy and express allocation intent, nothing about
capital adequacy, liquidity, leverage, order placement, risk, memory, or
NLP. This record covers the implementation decisions behind it, all made
*after* `StrategyDecision` itself was already frozen ([ADR-008](ADR-008-StrategyDecision-Contract.md)) —
every decision here is explicitly implementation, not contract, per that
ADR's own "freeze interfaces, not implementation" framing.

---

## Decision 1: `supports(regime_id)` is the only source of truth for dispatch

**Status**: Accepted

### Context

An earlier design considered a separate `regime_id -> strategy_id` map
(analogous to a routing table) living in `StrategyRegistry`, independent
of each `Strategy`'s own `supports()` method. That would have created two
places encoding "which regime does this strategy handle" that could drift
out of sync — exactly the kind of duplicated-source-of-truth problem this
platform's other contracts (e.g. `FeatureVector.feature_names`/
`Provenance.feature_versions` needing to agree, enforced in
`FeatureVector.__post_init__`) exist to avoid, not reproduce.

### Decision

`StrategyRegistry.resolve(regime_id)` linear-scans registered strategies
and calls `.supports(regime_id)` on each — there is no second, cached
routing table. Exactly one match returns that strategy; zero matches
(with no fallback configured) raises `UnsupportedRegimeError`; more than
one match raises `AmbiguousStrategyError` — dispatch must be
deterministic, and this milestone doesn't guess a priority order on a
caller's behalf.

### Consequences

- "Configuration override" (an explicit Milestone 5 test requirement) is
  just: construct a strategy instance with different `supported_regime_ids`
  — no separate map to keep in sync, verified by
  `tests/strategy/test_registry.py::TestResolve::
  test_configuration_override_changes_which_regime_ids_a_strategy_supports`.
- A misconfiguration (two strategies both claiming a regime) fails loudly
  at `resolve()` time, not silently picking whichever happened to be
  registered first.
- Trade-off, accepted: `resolve()` is O(n) in registered strategy count.
  Given this milestone's four reference strategies (and any realistic
  near-term count), this is not a practical concern — no premature
  optimization to a hash-map lookup until a real case demands it.

### Alternatives Considered

- **A `regime_id -> strategy_id` `Mapping` built alongside the registry**
  — rejected per Context: a second source of truth for the same fact.

---

## Decision 2: `allocate()` does not re-check `supports()` — a real bug caught during implementation

**Status**: Accepted

### Context

The first implementation had `RegimeMappedStrategy.allocate()`
independently re-verify `self.supports(regime_state.regime_id)` as a
"defense in depth" check. This directly broke
`StrategyEngineConfig.default_strategy_id`: the whole point of a fallback
strategy is that it gets called for a regime it does *not* declare direct
support for. A smoke test exercising the fallback path
(`registry.resolve(unmapped_regime_id, default_strategy_id=...)` followed
by `strategy.allocate(...)`) caught this immediately —
`UnsupportedRegimeError` raised even though `resolve()` had already,
correctly, decided to use that strategy.

### Decision

`allocate()` does not require `supports(regime_state.regime_id)` to be
`True`. `supports()` is purely a dispatch-time filter consumed by
`StrategyRegistry.resolve`; `RegimeMappedStrategy`'s actual allocation
formula never depended on `regime_id` being in `supported_regime_ids` in
the first place (it only echoes `regime_id` into the output). This is
documented explicitly in both `interfaces.Strategy.allocate`'s docstring
and `RegimeMappedStrategy.allocate`'s inline comment, so a future
strategy implementation doesn't reintroduce the same bug.

### Consequences

- `StrategyEngineConfig.default_strategy_id` works as designed: a
  strategy with `supported_regime_ids=frozenset()` (never matched via
  direct dispatch) can still be the fallback for every unmapped regime —
  see `strategies/defensive.py` and
  `tests/strategy/test_strategies.py::TestAllocate::
  test_allocate_does_not_require_supports_to_be_true`.
- `RegimeMappedStrategy.__post_init__` was changed to accept an empty
  `supported_regime_ids` (previously rejected as "must not be empty") —
  a strategy meant purely as a fallback has a legitimate reason to
  support nothing directly.
- This is recorded here rather than silently fixed and forgotten because
  it's a genuine design lesson: a validation that looks like harmless
  extra safety can silently contradict a feature built specifically to
  bypass it. The fix is the *removal* of a check, not the addition of one.

### Alternatives Considered

- **Route the fallback through a different method than `allocate()`** —
  rejected: would mean every `Strategy` implementation needs two entry
  points instead of one, for no benefit — `allocate()` already does the
  right thing once the redundant check is gone.

---

## Decision 3: Confidence propagates directly; allocation scales linearly with it

**Status**: Accepted

### Context

Milestone 5 has no independent signal beyond the regime call itself — no
sentiment, no bandit confidence, no separate model. `StrategyDecision.
confidence` and `.allocation` need some principled, deterministic
relationship to `RegimeState.confidence`, not an arbitrary constant.

### Decision

`RegimeMappedStrategy.allocate` sets `StrategyDecision.confidence =
RegimeState.confidence` directly (this strategy has no other information
to adjust it with), and `allocation = base_allocation *
RegimeState.confidence` — a low-confidence regime call produces a
proportionally smaller position, never the strategy's full
`base_allocation` regardless of how uncertain the HMM actually was.

### Consequences

- "Confidence propagation" (an explicit Milestone 5 test requirement) is
  a direct, traceable formula, not an opaque black box — verified by
  `tests/strategy/test_strategies.py::TestAllocate::
  test_allocation_scales_linearly_with_confidence`.
- `allocation` is provably always within `[0.0, 1.0]` given
  `base_allocation` and `confidence` both are (both already validated at
  construction) — `0.0 <= base * confidence <= 1.0` follows arithmetically,
  not just from `StrategyDecision`'s own bound check.
- Trade-off, accepted: this is a genuinely simple model. A future
  milestone bringing in additional signal sources (sentiment, bandit
  confidence) will need a real design decision — and its own ADR — for
  how those combine with regime confidence; this decision doesn't
  anticipate that.

### Alternatives Considered

- **A fixed allocation regardless of confidence** — rejected: throws away
  real information the HMM already computed, for no simplicity benefit
  worth the loss.

---

## Decision 4: `regime_id` semantics are always caller-supplied, never hardcoded

**Status**: Accepted

### Context

[Standards/RegimeState Contract.md](../../Standards/RegimeState%20Contract.md)
is explicit: `regime_id` is a raw HMM state index with no fixed meaning
across trained models — state `0` from one model is not "bull" in any
inherent sense, and isn't comparable to state `0` from a different model.
Milestone 5's own brief names strategy files `bull.py`/`bear.py`/
`sideways.py`/`defensive.py`, which risks implying these files know how
to detect a bull market from `regime_id` alone.

### Decision

None of the four reference strategy modules hardcode which `regime_id`
values they apply to. Each exposes a `create_*_strategy(strategy_id,
supported_regime_ids, ...)` factory — `supported_regime_ids` is always
supplied by the caller assembling a registry for a specific trained
model, typically after inspecting that model's fitted state
characteristics (mean return/volatility per state via `hmm.models.
TrainedModel`/`ModelMetadata`, though this milestone doesn't build that
inspection tooling itself). The file names (`bull.py`, etc.) are a
naming convention for readability and the *style* of allocation behavior
(aggressive vs. defensive), not a semantic claim about detection.

### Consequences

- Every module's docstring states this explicitly, so a future reader
  doesn't misread `bull.py` as "the code that finds bull markets."
- Retraining a model (which can permute which integer means what) doesn't
  silently corrupt strategy dispatch — the caller must re-derive
  `supported_regime_ids` for the new model, an explicit step rather than
  an assumption that survives silently across a retrain.
- Known gap, not solved here: no tooling exists yet to help an operator
  actually determine which `regime_id` is "bull-like" for a freshly
  trained model (e.g. inspecting `GaussianHMM.means_` per component). Left
  for whichever milestone first operationalizes model retraining/refresh
  (Known Gaps item 3).

### Alternatives Considered

- **Have each strategy self-detect regime character from `FeatureVector`
  content** (e.g. "positive returns and low volatility = bull") —
  rejected: this duplicates exactly the regime-detection job the HMM
  already does, and would let a strategy silently disagree with the
  `RegimeState` it was handed about what regime it's actually in.

---

## Verification note

While building the serialization round-trip tests this milestone's
`tests/contracts/` work package required, the pre-existing, independently
written UTC-timestamp validation checks in `market_data.models` and
`features.feature_vector` were consolidated onto the shared
`common.time.require_utc` helper (added but not yet applied during
Milestone 4). This is a pure refactor — no behavior change, confirmed by
the full existing test suite passing unmodified — done opportunistically
while those files were already being touched for this milestone's
`to_dict`/`from_dict` additions, not as separately-scoped work.

`FeatureVector`, `Provenance`, and `RegimeState` gained `to_dict`/
`from_dict` methods in this milestone (previously only `hmm.models.
ModelMetadata` had them) — additive, no version bump, but worth noting
these three contracts didn't support JSON serialization at all before
Milestone 5's own contract-compatibility testing requirement surfaced the
gap.
