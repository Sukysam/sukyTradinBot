# ADR-022: Health & Readiness Design

**Status**: Accepted
**Date**: 2026-07-14
**Milestone**: [12 (WP1) — Health & Readiness](../../../../PROJECT_STATUS.md)

## Context

Milestones 1–11 were each built around one frozen domain contract
(`FeatureVector`, `RegimeState`, ..., `FinalDecision`) via a two-stage
freeze-PR-then-implementation-PR cycle. Milestone 12 is different: it is
operational maturity work, not a new decision-pipeline stage. Per
explicit product-owner direction, forcing WP1 into that same
freeze-first cadence "would likely create an artificial abstraction," so
this record covers both the design and implementation decisions in one
PR — there is no separate contract-freeze ADR preceding this one.

The product owner did specify one stable operational model worth
documenting even without a full freeze cycle:

```
PlatformHealth { status, checks, timestamp, version, git_commit }
```

— "not a business-domain contract... but... small, stable, and useful
across monitoring, dashboards, and automation" — plus ten required
subsystem checks: configuration, market data, model artifacts, feature
registry, HMM model, strategy registry, risk service, execution
adapter, memory store, NLP pipeline.

## Decision

### 1. `PlatformHealth`/`HealthCheckResult` as a stable operational model, not a domain contract

`ops.models` implements the exact shape requested, with the same
construction-time-consistency discipline every domain contract in this
handbook already carries (`ExecutionDecision`'s `DecisionType`,
`ArbitrationOutcome`): `classify_status` is a single free function
computing the expected aggregate `HealthStatus` from a sequence of
`HealthCheckResult`s, called both by `PlatformHealth.__post_init__` (to
validate a caller-supplied `status`) and by `ops.health.evaluate_health`
(to compute it), so the two code paths can never silently disagree.
`HealthCheckResult.detail` must be non-empty — the same "never produce
an unexplained result" principle `StrategyDecision.reasoning`/
`ExecutionDecision.reasoning`/`LearningDecision.rationale`/
`FinalDecision.rationale` each already carry, applied here because a
health check that can't say *why* it passed or failed isn't useful for
on-call debugging.

### 2. File-structure consolidation: six proposed modules collapsed to five

The proposed layout was:

```
src/ops/
    health.py
    readiness.py
    startup.py
    status.py
    models.py
    interfaces.py
```

The implementation instead uses `models.py`, `interfaces.py`,
`checks.py`, `health.py`, `reporting.py`, `exceptions.py` — five modules
plus the models/interfaces pair. This is a deliberate consolidation, not
an oversight, made for the same reason `backtest`/`memory`/`nlp` each
collapsed the user's higher-level phase descriptions into fewer modules
than a literal one-file-per-concept reading would suggest:

- **"Readiness" is not a separate algorithm from "health."** It is
  health evaluated over a critical-checks subset — the same aggregation
  function (`evaluate_health`/`classify_status`) applies; only the input
  `checks` sequence differs (a readiness probe passes a subset). A
  dedicated `readiness.py` would duplicate `health.py`'s aggregation
  logic or import from it for no behavioral gain.
- **"Startup" is a thin fail-fast wrapper, not new logic.**
  `require_healthy` (in `health.py`) raises `UnhealthyPlatformError`
  when a report isn't `HEALTHY` — that is the entire startup gate. A
  separate `startup.py` would hold one function whose entire body calls
  into `health.py`.
- **"Status" is the rendering/reporting layer**, mirroring
  `backtest.reporting.generate_report`/`memory.evaluation.
  generate_evaluation_report`/`nlp.evaluation.generate_evaluation_report`'s
  own established "consumes the model, never shapes it, not a frozen
  contract itself" pattern. Named `reporting.py` here for exact
  consistency with that precedent, rather than introducing a new
  `status.py` naming convention this handbook hasn't used elsewhere.

`checks.py` was added (not in the original proposal) to hold the ten
required subsystem probes as a named, individually-testable factory
function each, separate from the generic `CallableHealthCheck` wrapper
they're all built from.

### 3. One generic `CallableHealthCheck`, ten named factories — not ten bespoke classes

`ops.checks.CallableHealthCheck` wraps any zero-argument `probe:
Callable[[], bool]`; `configuration_check`, `market_data_check`,
`model_artifact_check`, `feature_registry_check`, `hmm_model_check`,
`strategy_registry_check`, `risk_service_check`,
`execution_adapter_check`, `memory_store_check`, `nlp_pipeline_check`
each construct one, differing only in the `name` baked in. This balances
DRY (one execution/error-handling path, not ten copies of the same
try/except) against discoverability (each subsystem still gets a named,
individually-testable constructor) — the same trade-off
`risk.validators`'s "small, composable, one concern each" validators
already established as this codebase's preferred pattern over one large
generic parameterized validator.

Every factory takes the probe as an injected parameter — never
constructs a real Alpaca client, HMM model, or database handle
internally — the same dependency-injection convention `BacktestEngine.
run` (`git_commit`/`pipeline_versions` as explicit inputs, not
`subprocess` calls) established for this exact reason: a health check
must be testable without a live dependency, and must not silently
depend on process-global state.

### 4. A probe's exception becomes a failing `HealthCheckResult`, never propagates

`CallableHealthCheck.check()` catches any exception the probe raises and
converts it into `healthy=False` with the exception type/message in
`detail`, rather than letting it propagate. One unreachable subsystem
must not prevent the other nine from being reported — an aggregated
health report is only useful if it can describe a partial failure, not
just fail entirely the moment the first check does.

### 5. `OpsError`/`UnhealthyPlatformError`, no builtin-name workaround needed

`Ops` doesn't collide with a Python builtin (unlike `memory`, which
required `MemoryLoopError` instead of the ambiguous `MemoryError`), so
the plain `<Package>Error` convention applies without modification:
`OpsError(AppError)` as the package base, `UnhealthyPlatformError
(OpsError)` for `require_healthy`'s fail-fast gate.

## Consequences

- `evaluate_health`/`require_healthy` give production start-up code a
  two-line integration: build the ten checks with real probes, call
  `evaluate_health`, call `require_healthy`. A process that starts
  anyway despite a failing dependency check is exactly the kind of
  silent-no-op failure this exists to prevent.
- Because `checks.py`'s factories are just `CallableHealthCheck`
  constructors, adding an eleventh subsystem later is a contained,
  additive change — one new named function, no change to `models.py`,
  `health.py`, or any existing check.
- `readiness`/`startup` are deliberately *not* separate modules; if a
  genuine readiness-vs-liveness distinction (e.g. different failure
  thresholds, not just a different check subset) becomes necessary in a
  later work package, that would be a real behavioral difference
  justifying a new module — not the case today.
- `src/ops` has zero transitive third-party dependencies, same as
  `src/memory` and `src/nlp` Phase A — pure stdlib.
- Trade-off, accepted: `ops.checks`' ten factories give one process a
  full-platform view, but nothing in this milestone wires them to real
  probes (a live Alpaca connection check, an actual HMM-model-on-disk
  check, etc.) — that wiring belongs to whichever later work package
  introduces the deployment entrypoint that constructs them for real,
  not WP1 itself, which only had to prove the aggregation and reporting
  layer works correctly against injected probes.

## Alternatives Considered

- **Match the proposed six-file layout literally** — rejected: see
  Decision §2. Splitting health/readiness/startup/status into four
  separate modules when three of the four are thin wrappers around the
  same aggregation function would scatter one coherent concept across
  files for no behavioral benefit, the same reasoning that kept
  `memory`/`nlp` from splitting their own phases into more modules than
  the actual algorithms warranted.
- **Ten bespoke `HealthCheck` classes, one per subsystem** — rejected:
  every one of the ten would duplicate `CallableHealthCheck`'s
  try/except-and-convert logic with only the `name` and probe differing;
  the generic-wrapper-plus-named-factory split avoids that duplication
  while keeping each subsystem individually named and testable.
- **Let a failing probe's exception propagate out of `check()`** —
  rejected: a single unreachable subsystem would then abort the entire
  aggregation before the other nine checks even run, defeating the
  purpose of an aggregated report that is supposed to describe partial
  failure.
- **Construct real dependencies (Alpaca client, HMM model, etc.) inside
  the factory functions** — rejected: would make every check
  untestable without the real dependency present and would violate the
  DI convention this codebase has used since `BacktestEngine.run`; the
  probe is always injected, the factory only supplies the check's name.
