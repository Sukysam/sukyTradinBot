# ADR-001: Foundation

**Status**: Accepted
**Date**: 2026-07-12
**Milestone**: [1 — Foundation](../../../../PROJECT_STATUS.md)

## Context

Milestone 1 built the software foundation this repository's future
milestones sit on: packaging, dependency management, configuration,
structured logging, base interfaces, common utilities, Docker, CI, and
lint/format/type tooling — with an explicit brief of *no trading logic, no
HMM, no Alpaca, no broker, no strategies*. That brief, and the fact that
this is the one milestone every later one depends on, forced several
decisions that will be expensive to reverse once other code is built on
top of them. This record captures those decisions while the reasoning is
still fresh, per [ADR/README.md](README.md).

---

## Decision 1: `typing.Protocol` for base interfaces, not `abc.ABC`

**Status**: Accepted

### Context

`src/common/interfaces.py` needed to define `Clock`, `Service`, and
`HealthCheck` contracts for components that don't exist yet — future
milestones' consumers, plus test fakes — without forcing every future
implementation into an inheritance hierarchy.

### Decision

Use `typing.Protocol` (structural typing) with `@runtime_checkable` for
every foundation-level interface, matching the pattern
`regime-trader/main.py` already established for `MarketDataProvider`,
`ModelStore`, and `SignalGenerator`.

### Consequences

- A test fake (`FixedClock`, or any future `HealthCheck` fake) satisfies
  the contract just by matching the method signature — no base-class
  import, no `super().__init__()`, no inheritance coupling to `common`.
- Consistent with [Standards/Python Style Guide.md](../../Standards/Python%20Style%20Guide.md),
  which already documents this as the codebase's convention.
- Trade-off: `@runtime_checkable`'s `isinstance()` check only verifies
  method *presence*, not signature correctness — a class with a
  same-named but wrong-signature method would pass an `isinstance` check.
  Mitigated by strict MyPy (Decision 3), which does check signatures
  statically, and by tests that actually call the interface's methods
  rather than only asserting `isinstance`.

### Alternatives Considered

- **`abc.ABC` with abstract methods** — rejected. Forces every
  implementation to inherit from a `common`-owned base class, which is
  exactly the kind of coupling [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md)'s
  "dependency injection over hidden construction" principle argues
  against, and makes constructing a minimal test fake more ceremony than
  it needs to be.

---

## Decision 2: Pydantic + pydantic-settings for configuration

**Status**: Accepted

### Context

"Configuration system" and "Environment handling" were separate, explicit
Milestone 1 goals: typed settings, environment-variable and `.env` loading,
validation, and safe defaults (never silently defaulting to production).

### Decision

Use `pydantic` v2 + `pydantic-settings` for `common.config.Settings`,
rather than hand-rolled `os.environ` parsing.

### Consequences

- Env-var/`.env` loading, type coercion, `Literal`-based closed-set
  validation (`environment`, `log_format`), and immutability (`frozen`)
  all come for free, tested by a mature, widely-used library rather than
  reimplemented and re-tested from scratch.
- Adds two dependencies to the base `dependencies` list — a real cost for
  a "foundation" package meant to be lightweight, accepted because both
  goals it serves were explicit requirements, and because the alternative
  is a worse, less-tested version of the same functionality.
- Establishes `pydantic` as the toolkit for any future structured config
  or data-contract needs (e.g. a later `config/settings.yaml` schema for
  Milestone 2+ trading config) — a real, deliberate lock-in, not an
  accident.

### Alternatives Considered

- **`os.environ` + stdlib `dataclasses`** — rejected: reinvents
  validation, type coercion, and error messaging pydantic already
  provides, and error messages from hand-rolled parsing tend to be worse
  precisely where they matter most (a misconfigured production
  deployment).
- **`python-decouple` / `environs`** — smaller, narrower libraries;
  rejected because they don't offer the same growth path toward
  structured, nested, validated config that later milestones are likely
  to need once trading-specific settings are layered on.

---

## Decision 3: Strict MyPy (scoped to `src/` + `tests/`)

**Status**: Accepted

### Context

[Standards/Coding Standards.md](../../Standards/Coding%20Standards.md)
already requires type hints on all public functions. The foundation
package is what every later milestone imports, so a type error here has
the widest possible blast radius of anywhere in the repository.

### Decision

`mypy --strict`, applied to `src/` and `tests/` only (see Decision 6 for
why not repo-wide).

### Consequences

- Catches an entire class of bugs (missing `Optional` handling, incomplete
  type hints, `Any` leaking through) before runtime, and makes the
  `Protocol` interfaces from Decision 1 actually mean something —
  strict mode verifies an implementation's method signatures genuinely
  satisfy the `Protocol`, not just that the method exists.
- Real, one-time friction cost: writing foundation code under strict mode
  took a few extra minutes catching things like an unnecessarily broad
  `pytest.raises(Exception)` and an overly loose test assertion, both
  fixed during verification. That cost is paid once, now, while the
  foundation package is small — retrofitting strict mode onto a large,
  already-written codebase later would cost far more.
- Deliberately not applied to `regime-trader/`/`backtest/` yet — see
  Decision 6.

### Alternatives Considered

- **Default (non-strict) MyPy, or no type checking** — rejected. Given the
  Master Charter's "production-grade" vision and this package's role as
  the base every later milestone builds on, static type safety was judged
  table stakes, and cheaper to adopt now than to retrofit.

---

## Decision 4: Dependency injection over hidden construction

**Status**: Accepted

### Context

[00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md)'s Coding Standards
already mandate this ("any component with an external dependency ...
receives it as a constructor/function parameter"), and it's the pattern
`regime-trader/broker/order_executor.py` already uses (`TradingClient`
injected, never self-constructed). Milestone 1 had to decide whether the
foundation package would honor or quietly erode that convention.

### Decision

Every foundation component takes its dependencies explicitly:
`configure_logging(settings)` takes a `Settings` instance rather than
constructing its own; anything that needs "now" takes an injected `Clock`
(`SystemClock` in production, `FixedClock` in tests) rather than calling
`datetime.now()` internally.

### Consequences

- `FixedClock` makes any future time-dependent logic testable
  deterministically, without sleeping or monkeypatching — directly
  extending the "pass `as_of` explicitly" discipline
  [Standards/Python Style Guide.md](../../Standards/Python%20Style%20Guide.md)
  documents from `EquityTracker`/`LearningEngine`.
  `Settings(environment="test")` lets tests override configuration
  without touching real environment variables.
- Consistent style between `src/common` and `regime-trader/` means an
  engineer moving between the two doesn't context-switch conventions.
- Trade-off: slightly more verbose call sites (settings/clock must be
  threaded through explicitly rather than reached for globally). Accepted
  — the Master Charter already prioritizes this trade-off deliberately.

### Alternatives Considered

- **Module-level singletons** (a global `now()` everyone calls directly,
  a module-level configured logger) — rejected as the exact anti-pattern
  the anti-look-ahead and testability principles already warn against
  generalizing from `risk_manager.py`/`learning_engine.py`'s explicit
  `as_of` parameters.

---

## Decision 5: A separate `[trading]` extras group in `pyproject.toml`

**Status**: Accepted

### Context

`regime-trader/`'s existing modules import pandas, numpy, scipy,
hmmlearn, torch, transformers, `ta`, and alpaca-py — heavy,
domain-specific, slow-to-install dependencies. `src/common` imports none
of them.

### Decision

Declare those packages under `[project.optional-dependencies].trading` in
`pyproject.toml`, not the base `dependencies` list. Installable via
`pip install -e ".[trading]"`, but not pulled in by a plain
`pip install -e ".[dev]"`.

### Consequences

- Foundation-only installs (what CI and any Milestone-1-scoped work
  needs) stay fast and light — no multi-gigabyte `torch`/`transformers`
  download for someone only touching `common/`.
- Makes the "no trading logic" boundary machine-enforced, not just a
  sentence in a PR description: the dependency graph itself documents
  which packages belong to which concern.
- Trade-off: `regime-trader/` still isn't installable as a clean,
  standalone package via plain `pip install -e .` — accepted, because it
  isn't a properly structured package yet regardless (see Decision 6).

### Alternatives Considered

- **One flat `dependencies` list** — rejected: would force every
  foundation-only contributor and CI job to install the full ML/broker
  stack for no benefit, and would blur exactly the boundary this
  milestone was scoped to keep sharp.

---

## Decision 6: Do not touch `regime-trader/` (or `backtest/`) in this milestone

**Status**: Accepted

### Context

Milestone 1's brief was explicit and absolute: no trading logic, no HMM,
no Alpaca, no broker, no strategies. `regime-trader/` contains all of
those. A "production repository layout" goal could plausibly have been
read as license to restructure it (e.g. into a proper `src/regime_trader/`
package, fixing its hyphenated, non-importable directory name).

### Decision

Zero changes to `regime-trader/` or `backtest/` — no renames, no
reformatting, no import-path changes, not even mechanical or
whitespace-only touches. Verified via `git status` showing an empty diff
on both paths at the end of the milestone.

### Consequences

- Keeps the milestone's blast radius fully contained, trivially reviewable
  and revertible in isolation from any trading-logic change.
- Avoids the specific risk of a "harmless" rename or reformat silently
  introducing a subtle bug in code that wasn't being re-verified
  line-by-line as part of this work.
- Direct trade-off, tracked rather than hidden: `regime-trader/` and
  `backtest/` remain outside Ruff/Black/MyPy/CI coverage for now — see
  [Architecture/Known Gaps.md](../Known%20Gaps.md)'s "Tooling scope" note.
  Bringing them under the same tooling will need its own dedicated,
  separately reviewed change, likely including a one-time formatting/lint
  pass.

### Alternatives Considered

- **Migrate `regime-trader/` to `src/regime_trader/` now, as part of
  "production repository layout"** — considered and rejected for this
  milestone. Moving files and fixing import paths across every trading
  module is mechanically indistinguishable from "touching trading logic"
  even though no algorithmic content would change, and was judged
  higher-risk than deferring the packaging question to whichever future
  milestone (3, 5, 6, 8, or 9 per [PROJECT_STATUS.md](../../../../PROJECT_STATUS.md))
  is already modifying that code for substantive reasons.
