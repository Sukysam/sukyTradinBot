# ADR-024: Configuration & Secrets Design

**Status**: Accepted
**Date**: 2026-07-14
**Milestone**: [12 (WP3) — Configuration & Secrets](../../../../PROJECT_STATUS.md)

## Context

WP1 (ADR-022) established `PlatformHealth`; WP2 (ADR-023) built
metrics/tracing/logging/alerts on top of it, all reading `PlatformHealth`
as the single operational model. WP3 is scoped around the product
owner's proposed pipeline:

```
Environment -> Configuration -> Secret Sources -> Validation -> ValidatedRuntime
```

with responsibilities "configuration loading, environment validation,
secret resolution, startup validation, fail-fast errors, runtime
identity" — explicitly *operational* configuration, not business
configuration, extending `src/ops/` rather than a new top-level package,
per direct instruction. The product owner also asked for a single
immutable runtime object, `RuntimeContext{platform_info, validated_config,
startup_time, environment, git_commit}`, as "the operational equivalent
of your domain contracts."

The proposed four-module layout was:

```
ops/
    config_runtime.py
    secrets.py
    validation.py
    startup.py
```

This record covers where each responsibility actually landed, and two
deliberate departures from the literal proposal: no `config_runtime.py`,
and `RuntimeContext`'s shape differs slightly from what was specified.

## Decision

### 1. No `config_runtime.py` — `common.config.Settings` already is "Configuration"

The first step of the proposed pipeline, "Environment → Configuration,"
already exists: `common.config.Settings` (Milestone 1) loads
`ENVIRONMENT`/`LOG_LEVEL`/`LOG_FORMAT`/`APP_NAME` from environment
variables via `pydantic-settings`, with the exact safe-by-default
behavior this kind of module needs (`environment` never silently
defaults to `production`). Rebuilding that loading mechanism inside
`ops` would duplicate a mechanism that already exists and is already
used elsewhere in this codebase (`market_data.auth.AlpacaCredentials`
follows the identical `pydantic_settings.BaseSettings` pattern).

Instead, `ops.startup.build_runtime_context` accepts `environment: str`
as a plain parameter — the caller (a real deployment entrypoint, not
built in this work package) is expected to pass `Settings().environment`.
This has a second consequence worth stating plainly: `common.config`
depends on `pydantic`/`pydantic-settings`; if `ops` imported `Settings`
directly, `ops` would transitively gain that dependency, breaking the
"zero transitive third-party dependencies" property every WP1/WP2 ADR
and the CHANGELOG have stated as true of this package. Accepting a
plain `str` instead of a `Settings` object keeps that property intact
through WP3 as well.

### 2. `RuntimeContext` excludes `validated_config` and a duplicate `git_commit`

The proposed shape was `RuntimeContext{platform_info, validated_config,
startup_time, environment, git_commit}`. The implementation is
`RuntimeContext{platform_info, environment, startup_time}` — two fields
narrower, deliberately:

- **No `validated_config` field.** "Validated" is represented
  structurally rather than as data: `ops.startup.build_runtime_context`
  is the only function that constructs a `RuntimeContext`, and it will
  not return one unless `ops.validation.require_valid_runtime` passed.
  A `RuntimeContext` existing *is* the proof that validation succeeded
  — there is no separate boolean or token that could go stale relative
  to the object holding it, the same reasoning `ops.models.
  classify_status` already applied to `PlatformHealth.status` (derive
  it, don't let it drift from what it's supposed to summarize).
- **No `git_commit` field.** `RuntimeContext.platform_info.git_commit`
  is already that value — a build's commit doesn't change based on
  which environment it's deployed to. Adding a second `git_commit`
  field directly on `RuntimeContext` would create exactly the kind of
  duplicated-source-of-truth risk this handbook's contracts have
  consistently avoided (compare `FinalDecision` choosing not to
  duplicate fields already present on its `SignalInput`s).

`RuntimeContext` also, by design, never carries the resolved secret
*values* themselves — only proof (via its own existence) that every
required one resolved. An object meant to be passed around widely
(health checks, metrics, logging, deployment tooling all read it, per
the product owner's own framing) is exactly the kind of object that
eventually gets logged, serialized, or included in an error report;
holding raw or even wrapped secret material on it would make every one
of those consumers a potential leak surface. Secret values, once
resolved, are used at the point of resolution (e.g. to authenticate a
provider) and not threaded further through this object.

### 3. `ops.secrets`: injectable `SecretSource`, no backend dependency

`SecretSource` is a `Protocol` (`get(name) -> str | None`);
`EnvSecretSource` reads `os.environ` — the same source
`common.config.Settings` and `market_data.auth.AlpacaCredentials`
already read credentials from, so this doesn't introduce a second,
competing convention for where secrets live. No Vault/AWS Secrets
Manager/similar client dependency: no secret backend has been chosen
for this platform, and choosing one now, inside an operational-tooling
work package, would commit to a vendor ahead of that decision — the
identical reasoning ADR-023 gave for deferring a real tracing-SDK
integration in `ops.tracing`. Swapping in a real backend later means
writing one new `SecretSource` implementation; no caller of
`resolve_secret`/`validate_runtime`/`build_runtime_context` changes.

`SecretValue` wraps a resolved value so it can be passed around without
ever being accidentally logged — `__repr__`/`__str__` are redacted;
`reveal()` is the one explicit, grep-able way to read the actual value.
This is a genuinely new safety mechanism this codebase didn't have
before (`AlpacaCredentials.secret_key` today is a plain `str`, printable
by accident); it is not retrofitted onto existing credential loaders in
this work package — that would be a wiring change to `market_data`, out
of scope for `ops`.

### 4. `ops.validation`: same report/gate split as `ops.health`

`validate_runtime` returns a `ValidationResult` (never raises); it
collects every failure in one pass rather than stopping at the first,
so a misconfigured environment surfaces its complete list of problems
on one restart rather than one problem per restart attempt.
`require_valid_runtime` is the corresponding gate, raising
`RuntimeValidationError` — structurally identical to `ops.health.
evaluate_health`/`require_healthy`'s split, so a reader who already
understands WP1's health-check flow already understands WP3's
validation flow.

### 5. `ops.startup.build_runtime_context`: orchestration only, health checks optional

The full proposed flow — "Load config → Resolve secrets → Validate →
Health checks → Platform ready" — is implemented as one function that
calls `ops.validation.validate_runtime`/`require_valid_runtime`, then
*optionally* `ops.health.evaluate_health`/`require_healthy` (only when
a non-empty `checks` sequence is passed; `PlatformHealth` cannot be
constructed from an empty check list, and no real subsystem probes are
wired to this function in this work package — matching WP1's own
"wiring not yet authorized" deferral for its ten check factories), and
finally constructs the `RuntimeContext`. `build_runtime_context` defines
no validation or health logic of its own — every step delegates to a
mechanism another module already owns, the same "startup is a thin
wrapper, not a new algorithm" role `ops.health.require_healthy` already
played for WP1.

## Consequences

- WP4 (Deployment) has exactly the single startup entrypoint the
  product owner asked for: `build_runtime_context(version=..., git_commit=...,
  environment=..., required_secrets=..., checks=...)` returning a
  `RuntimeContext` or raising a specific, catchable exception
  (`RuntimeValidationError` or `UnhealthyPlatformError`) naming exactly
  what's wrong.
- `src/ops` remains pure stdlib after WP3 — `SecretSource`/
  `EnvSecretSource`/`SecretValue` are hand-rolled, same as WP2's
  `Counter`/`Gauge`/`Span`/`Tracer`.
- Adding a new required secret to a future deployment is additive: pass
  its name in `required_secrets`, no change to `ops.secrets`,
  `ops.validation`, or `ops.startup`.
- Trade-off, accepted: `build_runtime_context` does not itself decide
  *which* secrets are required or *which* checks to run — that's the
  caller's job (a real deployment entrypoint, still not built).
  `ops` provides the mechanism; a later work package (WP4) provides the
  actual list.

## Alternatives Considered

- **Build `config_runtime.py` as a wrapper around `common.config.Settings`**
  — rejected: see Decision §1. A wrapper that just re-exposes
  `Settings.environment` under a new name adds an indirection with no
  behavioral value, and importing `Settings` directly would cost `ops`
  its zero-third-party-dependency property for no corresponding gain.
- **Give `RuntimeContext` a `validated_config` field holding the actual
  `Settings` object** — rejected: see Decision §1 and §2. Would also
  reintroduce the `pydantic` dependency into `ops.models`, the one
  module every other `ops` module imports from.
- **Store resolved `SecretValue`s on `RuntimeContext` for later reuse**
  — rejected: see Decision §2. Turns a widely-passed-around object into
  a leak surface for exactly the material `SecretValue` exists to
  protect; a caller that needs a secret value should resolve it at the
  point of use, not thread it through an unrelated identity object.
- **Depend on a real secrets-manager client (Vault, AWS Secrets Manager,
  etc.)** — rejected for this work package, same reasoning as ADR-023's
  tracing-SDK deferral: no backend has been chosen, and choosing one now
  would be a vendor decision made inside operational-tooling work, not
  an explicit, reviewed architecture decision.
- **Make health-check evaluation mandatory inside `build_runtime_context`**
  — rejected: would force every caller (including every test in this
  work package) to construct ten real `HealthCheck` probes before it
  could build a `RuntimeContext` at all, months before those probes are
  wired to anything real. Optional `checks`, empty by default, lets the
  mechanism exist now and the real wiring land whenever WP4 needs it.
