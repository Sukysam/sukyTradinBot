# ADR-023: Observability Design

**Status**: Accepted
**Date**: 2026-07-14
**Milestone**: [12 (WP2) — Observability](../../../../PROJECT_STATUS.md)

## Context

WP1 (ADR-022) established `PlatformHealth` as a stable operational
model and `ops.health.evaluate_health` as the one place that computes
it. Per direct product-owner review of WP1: "Now that `PlatformHealth`
exists, I'd make it the single operational model used by everything
else... Rather than each subsystem recomputing health independently."
WP2 (Observability) is scoped narrowly around that instruction —
metrics, tracing, structured operational logging, and alert rule
evaluation, all reading `PlatformHealth` rather than each inventing its
own notion of platform state. Dashboards are explicitly out of scope
per the same review ("Dashboards should consume exported metrics rather
than being part of the runtime").

The product owner proposed a four-module layout:

```
src/ops/
    metrics.py
    tracing.py
    logging.py
    alerts.py
```

with responsibilities listed as "structured metrics, tracing hooks,
operational counters, alert rule evaluation" — four responsibilities
against four files, but not a strict one-to-one mapping in the original
text. This record covers where each responsibility actually landed and
why, plus a new `PlatformInfo` model the product owner requested to
pair with `PlatformHealth`.

## Decision

### 1. `PlatformInfo`: static build identity, deliberately separate from `PlatformHealth`

`ops.models.PlatformInfo{version, git_commit, build_time, python_version}`
is a new frozen model, added exactly as specified. It is *not* folded
into `PlatformHealth` despite the overlap in fields (`version`,
`git_commit` appear on both): `PlatformHealth` is re-evaluated on every
call to `evaluate_health` (a check can flip between two evaluations),
while `PlatformInfo` describes the running process's build identity,
which does not change for the process's lifetime. Conflating the two
would make every metrics export / log line / alert that only needs
build identity pay the cost of re-running ten health checks it doesn't
need. Follows the same `to_dict`/`from_dict` and construction-time
validation convention (non-empty fields, UTC-normalized `build_time`)
every other `ops` model already carries.

### 2. "Operational counters" landed in `metrics.py`, not `logging.py`

The proposed responsibility list put "operational counters" as a
distinct item from "structured metrics," suggesting (but not strictly
requiring) a fourth home for it. A `Counter` is a metrics-domain
primitive — Prometheus, StatsD, and every comparable system model
"how many times did X happen" as a counter metric, not a logging
concern. Splitting it into `logging.py` would mean two files both claim
ownership of "how many times something happened," with no clean
boundary between them. `metrics.py` owns `Counter` and `Gauge` (the
complementary primitive: "current value of something"), a
`MetricsRegistry` (get-or-create semantics, so unrelated call sites
recording the same metric name are guaranteed to share one series, not
silently create two disconnected ones), `record_health_metrics`
(reads a `PlatformHealth`, writes one gauge per check plus one
aggregate status gauge — the "Metrics → PlatformHealth → Exporter"
pipeline from the WP1 review, made concrete), and
`export_prometheus_text` (hand-written Prometheus exposition-format
text, no `prometheus_client` dependency — `ops` remains pure stdlib,
same as `memory`/`nlp` Phase A and WP1).

### 3. `logging.py` is *operational event* logging, not a `common.logging` competitor

`ops.logging.log_health_status`/`log_alert` emit two specific,
structured event types (`health_status`, `alert_fired`) through a
caller-supplied `logging.Logger`, using the `extra=` mechanism
`common.logging.JSONFormatter` already knows how to flatten into the
production JSON log format. This module does not call
`logging.basicConfig`, install a handler, or otherwise reconfigure
anything — `common.logging.configure_logging` remains the one place
that decision is made, per that module's own stated scope. `ops.logging`
only defines what these two operational events look like on the wire,
the same "define the shape, inject the sink" split every other `ops`
module uses (`ops.checks`' injected probes, `ops.tracing`'s injected
hooks).

### 4. `tracing.py`: hook-based, zero-dependency, no SDK integration

`Span{name, started_at, ended_at, metadata}` plus `duration_seconds` as
a derived property; `Tracer.span()` is a context manager that times its
block and calls every registered hook with the completed `Span`. No
OpenTelemetry/Jaeger/etc. client dependency — a real backend
integration is meaningful only once a real backend is chosen, which is
not a decision this work package is positioned to make. What `Tracer`
gives instead is the same shape every future integration would need
underneath it anyway (a timed, named span, a hook to receive it), so
adopting a real SDK later means writing one new hook, not restructuring
any instrumented call site. Hooks run in registration order and a
raising hook propagates immediately — consistent with this codebase's
"fail loudly, never swallow silently" convention; a tracer that
silently dropped a hook's exception would hide a real bug in
observability code, which is exactly the code path most likely to run
unattended in production.

### 5. `alerts.py`: the same "generic wrapper, named factories" pattern as `ops.checks`

`CallableAlertRule` wraps an injected `predicate`/`detail` pair (plus a
`Clock`, for deterministic `triggered_at` in tests); `unhealthy_platform_rule`/
`degraded_platform_rule` are two named factories built on it —
structurally identical to `ops.checks`' `CallableHealthCheck` +
ten named subsystem factories from WP1. `evaluate_alerts(health, rules)`
evaluates every rule against one `PlatformHealth`, returning only the
`Alert`s that fired. Alerting reads `PlatformHealth` exclusively — no
rule constructs its own health judgment, matching the WP1 review's
central instruction for this work package.

## Consequences

- Every WP2 module now has the same shape of entrypoint: something that
  reads a `PlatformHealth` (or, for `PlatformInfo`, nothing at all) and
  produces one artifact — a metric, a log line, an alert. None of the
  four modules import each other for control flow; `ops.logging.log_alert`
  takes an `Alert` value, not an `AlertRule`, so `logging.py` and
  `alerts.py` stay decoupled aside from that one shared type.
- Adding an eleventh health check (WP1) or a third alert rule (WP2)
  later is additive in both cases — a new named factory function, no
  change to `evaluate_health`, `evaluate_alerts`, or any existing
  check/rule. The two packages' extensibility story is now identical by
  construction, not by coincidence.
- `src/ops` remains pure stdlib after WP2 — `Counter`/`Gauge`, `Span`/
  `Tracer`, and `Alert`/`CallableAlertRule` are all hand-rolled rather
  than pulling in `prometheus_client`/`opentelemetry-*`. This keeps the
  "zero transitive third-party dependencies" property WP1 established,
  at the cost of not natively speaking any specific backend's wire
  protocol beyond the Prometheus *text* format (which needs no client
  library to produce).
- Trade-off, accepted: `MetricsRegistry` is a single in-process
  instance with no thread-safety guarantees and no built-in HTTP
  exposition endpoint — wiring it behind a real `/metrics` endpoint (or
  a push gateway) belongs to WP4 (Deployment), which is the work
  package that actually stands up runtime HTTP surface area, not WP2.
- Trade-off, accepted: `Tracer`'s hooks run synchronously, in-process,
  in the same call stack as the traced work — there is no batching,
  async export, or sampling. Fine for the low-volume operational spans
  this platform currently has reason to trace (health evaluation,
  startup); would need reconsideration before tracing a hot path.

## Alternatives Considered

- **Fold `PlatformInfo` into `PlatformHealth`** — rejected: see Decision
  §1. Different re-computation cadence and different consumers (a
  `/version` endpoint never needs to run ten health checks) argue for
  keeping them separate, paired-but-independent models.
- **Put `Counter`/`Gauge` in `logging.py` as "operational counters," per
  the literal responsibility list** — rejected: see Decision §2. A
  counter is a metrics primitive in every comparable system this
  platform might eventually export to; splitting it away from
  `Gauge` (its natural complement) into a differently-named file would
  separate two primitives that belong together and are used together
  in `record_health_metrics`.
- **Depend on `prometheus_client` for metrics, or an OpenTelemetry SDK
  for tracing** — rejected for this work package: no backend has been
  chosen yet, and adding either dependency now would commit the
  platform to a specific vendor/protocol before WP4 (Deployment) even
  decides how metrics/traces leave the process. The hand-rolled
  primitives here give the same shape without that commitment; swapping
  in a real client later replaces the internals of `metrics.py`/
  `tracing.py`, not any instrumented call site.
- **Give `MetricsRegistry` an HTTP exposition endpoint directly** —
  rejected: `ops` has no HTTP-serving code anywhere, and adding a first
  one just for `/metrics` would pull in a web framework dependency for
  a single route, ahead of WP4's actual deployment/runtime-surface
  design. `export_prometheus_text` returns a string; whatever serves it
  is a later, explicit decision.
