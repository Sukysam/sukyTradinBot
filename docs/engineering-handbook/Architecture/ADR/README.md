# Architecture Decision Records (ADRs)

This folder records *why* a significant, hard-to-reverse engineering
decision was made — not what the code does (docstrings do that per
[Standards/Python Style Guide.md](../../Standards/Python%20Style%20Guide.md))
and not current status (that's [PROJECT_STATUS.md](../../../../PROJECT_STATUS.md)).
An ADR exists so that months from now, when someone asks "why did we do
it this way," the answer is a document, not a half-remembered Slack
thread or a git-blame archaeology session.

## Index

One or two sentences per ADR — enough to know whether it's the one you
need before opening it. Update this table in the same change that adds a
new ADR or changes an existing one's status.

| ADR | Status | Summary |
|---|---|---|
| [001 — Foundation](ADR-001-Foundation.md) | Accepted | Milestone 1's foundational choices: `Protocol`-based interfaces, Pydantic settings, strict MyPy, dependency injection, the `trading` extras group, and why `regime-trader/` was deliberately left untouched. |
| [002 — Market Data](ADR-002-Market-Data.md) | Accepted | Milestone 2: a new, independently-tooled `src/market_data` package (not `regime-trader/broker/`), provider-agnostic models behind `Protocol` interfaces, Parquet+DuckDB storage, and a thin adapter bridging `market_data` into `regime-trader/`'s existing contract. |
| [003 — Feature Engineering](ADR-003-Feature-Engineering.md) | Accepted | Milestone 3: the canonical `FeatureVector` output every consumer is meant to share, registration-time look-ahead protection for every feature, reuse of `market_data.validation` for bar cleaning, causal swing-point detection, and a generated-but-checked-in feature manifest. |
| [004 — FeatureVector Contract Freeze](ADR-004-FeatureVector-Contract-Freeze.md) | Accepted | Freezes `FeatureVector` as a stable, versioned interface ahead of Milestone 4 — required fields, ordering guarantees, and a backward-compatibility policy, so future changes are additive or explicitly versioned, never silent. |
| [005 — FeatureVector Provenance](ADR-005-FeatureVector-Provenance.md) | Accepted | Adds a required `provenance` field to `FeatureVector` (pipeline/manifest/feature versions, generation time, source dataset) for reproducibility and training/inference consistency checks — bumps the contract to v2. |
| [006 — RegimeState Contract](ADR-006-RegimeState-Contract.md) | Accepted | Freezes `RegimeState` — the HMM's only output type — as a stable interface ahead of Milestone 5, before any real consumer exists. |
| [007 — HMM Design](ADR-007-HMM-Design.md) | Accepted | Milestone 4's modeling and engineering decisions: porting the causal Forward Algorithm/BIC selection from `regime-trader/core/hmm_engine.py`, explicit missing-value handling, always computing both BIC and AIC, filesystem persistence, hard-fail feature-version drift detection at inference, and what's deliberately deferred (incremental live inference, `main.py.ModelStore` wiring). |
| [008 — StrategyDecision Contract](ADR-008-StrategyDecision-Contract.md) | Accepted | Freezes `StrategyDecision` — the Strategy Engine's only output type — as a stable interface *before* `src/strategy/` exists at all, a stricter sequencing than ADR-006/ADR-004's freezes. `allocation` bounded to `[0.0, 1.0]` and `reasoning` required-non-empty enforce existing invariants (long-only, always-explainable) at the type level. |
| [009 — Strategy Engine Design](ADR-009-Strategy-Engine-Design.md) | Accepted | Milestone 5's implementation decisions: `supports()`-only registry dispatch with no redundant routing map, the fallback-vs-direct-dispatch bug found and fixed during smoke testing (`allocate()` must not re-check `supports()`), the confidence-propagation formula, and why `regime_id` semantics are always caller-supplied, never hardcoded in a strategy module. |
| [010 — ExecutionDecision Contract](ADR-010-ExecutionDecision-Contract.md) | Accepted | Freezes `ExecutionDecision` — the Risk Manager's only output type — as a stable interface *before* `src/risk/` exists, grounded in `core/risk_manager.py`'s real `VetoDecision`/`CircuitBreakerDecision` shapes and `Standards/Risk Limits Reference.md`'s actual limits. `approved_allocation` bounded to `[0.0, strategy_reference.allocation]` enforces "risk only ever reduces size, never increases it"; a size-cut approval must always carry a `risk_adjustments` reason, closing a real gap in the legacy `VetoDecision`. An explicit `decision_type` (`APPROVED`/`REDUCED`/`REJECTED`) classifies every decision, validated at construction against the other fields. |
| [011 — Risk Manager Design](ADR-011-Risk-Manager-Design.md) | Accepted | Milestone 6's implementation decisions: a real redundancy bug found via testing (four exposure/leverage validators sharing thresholds with `ExposureCapacitySizing` made the `REDUCED` decision type structurally unreachable — fixed by excluding them from `RiskService.default()`'s validator set), the validators→sizing→circuit-breakers pipeline order and why it's outcome-equivalent to the legacy circuit-breakers-first order, float-precision handling for `decision_type` classification, minimal `AccountState`, and what's deliberately deferred (per-trade dollar risk, correlation filtering, a real liquidity check — all need data no current input provides). |
| [012 — OrderIntent Contract](ADR-012-OrderIntent-Contract.md) | Accepted | Freezes `OrderIntent` — the Execution Layer's only output type — as a stable, broker-agnostic interface *before* `src/execution/` exists. Every field type is first-party (never an Alpaca SDK type); `stop_loss` is mandatory for a `BUY`, forbidden for a `SELL`; `idempotency_key` is caller-supplied, never broker-generated. Surfaces a real, unresolved gap: neither `StrategyDecision` nor `ExecutionDecision` carries price information, so sourcing `reference_price`/`stop_loss` is documented as open Milestone 7 implementation work, not solved by this freeze. |
| [013 — Execution Layer Design](ADR-013-Execution-Layer-Design.md) | Accepted | Milestone 7's implementation decisions: `ExecutionContext`/`FeatureSnapshot` as deliberately unfrozen internal value objects ("execution contracts describe trading intent, not market observations"), four pluggable Protocols (`MarketSnapshotProvider`/`FeatureSnapshotProvider`/`StopLossPolicy`/`BrokerAdapter`) with `BrokerAdapter` structurally isolated from `ExecutionService`, `router.py`'s target-allocation-vs-current-position reconciliation and its documented sell-side approximation, and result-to-exception bridging so broker retries reuse `common.retry` with a caller-supplied, genuinely idempotent `idempotency_key`. |
| [014 — BacktestResult Contract](ADR-014-BacktestResult-Contract.md) | Accepted | Freezes `BacktestResult` — the Backtesting & Validation layer's only output type — as a stable interface *before* `src/backtest/` exists. The first run-level (not single-event) contract in this handbook: `trade_log`/`equity_curve` are frozen as part of the contract itself, not left unfrozen like Milestone 7's `ExecutionContext`, since golden-dataset regression testing needs them. `TradeRecord` carries `strategy_id`/`regime_id`/`holding_period` explicitly so Milestone 9 can compare realized vs. `StrategyDecision.expected_holding_period`. Degenerate ratios (`calmar_ratio`, `profit_factor`) are `float("inf")`, matching `PortfolioState.gross_exposure_pct`'s existing convention. Embeds a `ReplayRun` reproducibility record (`run_id`, `dataset`, `pipeline_versions`, `git_commit`, `timestamp`), added during review so a future regression can be traced to its exact cause. |
| [015 — Backtesting Engine Design](ADR-015-Backtesting-Engine-Design.md) | Accepted | Milestone 8's implementation decisions: a two-phase build (deterministic replay proven before any metric was computed), fills at the bar's own open to avoid look-ahead (invariant #1), `PortfolioEngine` kept mutable and separate from `replay.py` for future paper-trading reuse, lockstep multi-symbol replay requiring aligned timestamps, metrics grouped into `returns`/`risk`/`exposure`/`trade_quality`, a pre-replay equity-curve seed point closing a real bug found via testing, `git_commit`/`pipeline_versions` as explicit inputs rather than a hidden subprocess call, and a golden-dataset regression test using documented tolerance (not exact equality) given real cross-numpy-version HMM training variance across this project's own CI matrix. |
| [016 — LearningDecision Contract](ADR-016-LearningDecision-Contract.md) | Accepted | Freezes `ExperienceRecord` and `LearningDecision` — the Adaptive Learning / Memory Loop's two output types — as stable interfaces *before* `src/memory/` exists. Adapts, rather than ports, the legacy `regime-trader/core/learning_engine.py` contextual-bandit design: same Thompson-Sampling-over-Beta-posteriors formulation, narrower `(strategy_id, regime_id)` context, and a hard shadow-mode guarantee — no code path in Milestone 9 lets a `LearningDecision.recommended_allocation` reach `strategy`/`risk`/`execution`. SHAP-based `rationale` and a LightGBM policy are both explicitly deferred in favor of a simple posterior summary and the same bandit formulation the legacy code already validated. |
| [017 — Memory Loop Design](ADR-017-Memory-Loop-Design.md) | Accepted | Milestone 9's implementation decisions, built in three independently-verified phases (Experience Store → bandit → evaluation): `InMemoryExperienceStore`/`JsonlExperienceStore` as an immutable, append-only, single-writer log; `ThompsonSamplingPolicy`/`BetaArm` reusing the legacy bandit's exact update rule with a caller-injected `random.Random` for determinism; `recommended_allocation = production_allocation * sampled_weight` (a scaling model, never an independently larger allocation); `confidence` derived from sample size, not posterior variance; a thin `MemoryService` entry point; and `memory.evaluation`'s agreement-rate/drift/simulated-P&L/cumulative-regret comparison reporting, which reads history but never mutates it. |
| [018 — NewsSignal Contract](ADR-018-NewsSignal-Contract.md) | Accepted | Freezes `NewsSignal` — the NLP & Event Processing layer's only output type — as a stable interface *before* `src/nlp/` exists. Adapts, rather than ports, the legacy `regime-trader/core/sentiment_engine.py` (`SentimentScore`, FinBERT) and `regime-trader/broker/news_streamer.py` (`NewsItem`) shapes: the three-probability-plus-label sentiment shape and its `[0.99, 1.01]` sum tolerance carry over unchanged, `sentiment_label` gains a new type-level argmax-consistency check, and a hard shadow-mode guarantee — no code path in Milestone 10 lets a `NewsSignal` reach `strategy`/`risk`/`execution`. Only the pipeline stages that *produce* `NewsSignal` (ingestion, cleaning, deduplication) are left deliberately unfrozen; FinBERT scoring and SHAP attribution are both phased later (ingestion first). |
| [019 — NLP News Engine Design](ADR-019-NLP-News-Engine-Design.md) | Accepted | Milestone 10's implementation decisions, built in three independently-verified phases (ingestion → sentiment → evaluation): `InMemoryNewsItemStore`/`JsonlNewsItemStore` deduplicating on `(source, source_id)`; a batch-only `SentimentScorer` Protocol with no single-headline method (architecturally preventing the per-headline scoring anti-pattern); `DeterministicSentimentScorer` (dependency-free, used by every Phase B/C test) and `FinBertSentimentScorer` (adapts the legacy engine, lazy `torch`/`transformers` import, `@pytest.mark.integration`-gated tests that skip gracefully without the `trading` extra); entity extraction deliberately deferred (`entities=()` always, in this milestone); `nlp.evaluation`'s ingestion-latency/deduplication-rate/sentiment-distribution/throughput reporting, read-only. |
| [020 — FinalDecision Contract](ADR-020-FinalDecision-Contract.md) | Accepted | Freezes `FinalDecision`/`SignalInput` — Signal Orchestration's arbitration output — as a stable interface *before* `src/orchestration/` exists. The first milestone whose whole purpose is reconciling `StrategyDecision` (primary), `LearningDecision`, and `NewsSignal` (both advisory) rather than producing an independent opinion: `final_allocation` is type-level bounded to `[0.0, primary_allocation]` — mirroring `ExecutionDecision.approved_allocation`'s bound one layer earlier — so no arbitration policy can let an advisory signal manufacture conviction the Strategy Engine never had. `outcome` (`CONFIRMED`/`ADJUSTED`/`SUPPRESSED`) is validated against the allocation fields at construction, the same discipline `ExecutionDecision.decision_type` established. Explicitly does **not** authorize wiring `FinalDecision` into `RiskService` in place of `StrategyDecision` — that remains a separate, later, explicitly-reviewed decision. |
| [021 — Signal Orchestration Design](ADR-021-Signal-Orchestration-Design.md) | Accepted | Milestone 11's implementation decisions, built in three independently-verified phases (arbitration → policies → evaluation): a single-method `ArbitrationPolicy` Protocol behind four genuinely distinct mechanisms — `SafetyFirstPolicy` (Phase A's original rule: two disagreements suppress), `ConsensusPolicy` (stricter: any disagreement suppresses), `WeightedVotePolicy` (continuous blend, structurally can never fully suppress as long as `strategy_weight > 0`), `ConfidencePolicy` (scales by relative confidence, independent of agreement direction); `arbitrate` defaults to `SafetyFirstPolicy` for Phase A backward compatibility; `orchestration.signals` centralizes agreement/context logic so all four policies share it; `orchestration.evaluation` reads paired `(FinalDecision, LearningDecision, NewsSignal)` history (not `FinalDecision` alone) for agreement-rate/signal-conflict-rate/divergence/news-alignment/confidence/override-frequency reporting, read-only. |
| [022 — Health & Readiness Design](ADR-022-Health-And-Readiness-Design.md) | Accepted | Milestone 12 WP1: the first ADR in this handbook covering both design and implementation in one record — operational maturity work, not a domain-decision milestone, so there is no preceding contract-freeze ADR. Documents the stable (but not domain-contract) `PlatformHealth`/`HealthCheckResult` operational model, `classify_status` as the single source of truth cross-checked at construction and by `evaluate_health`, one generic `CallableHealthCheck` behind ten named subsystem factories (configuration/market data/model artifacts/feature registry/HMM model/strategy registry/risk service/execution adapter/memory store/NLP pipeline), and the deliberate consolidation of the proposed six-module layout into five (`readiness`/`startup`/`status` are facets of the same aggregation, not separate algorithms). |
| [023 — Observability Design](ADR-023-Observability-Design.md) | Accepted | Milestone 12 WP2: `PlatformInfo{version, git_commit, build_time, python_version}` pairs with `PlatformHealth` but stays a separate model (different recomputation cadence). `ops.metrics` (`Counter`/`Gauge`/`MetricsRegistry`, `record_health_metrics`, hand-written Prometheus-text `export_prometheus_text`, zero third-party dependencies), `ops.tracing` (`Span`/`Tracer`, hook-based, no SDK integration), `ops.logging` (structured `health_status`/`alert_fired` events built on `common.logging`'s existing JSON formatter, no parallel logging config), `ops.alerts` (`CallableAlertRule` + named `unhealthy_platform_rule`/`degraded_platform_rule` factories, mirroring `ops.checks`' generic-wrapper-plus-named-factories pattern). Every module reads `PlatformHealth` as the single operational model; none recomputes health independently. |
| [024 — Configuration & Secrets Design](ADR-024-Configuration-And-Secrets-Design.md) | Accepted | Milestone 12 WP3: no `config_runtime.py` — `common.config.Settings` already is "Configuration," so `ops.startup.build_runtime_context` accepts a plain `environment: str` rather than importing `Settings` (keeps `ops` free of the `pydantic` dependency). `ops.secrets` (`SecretSource` Protocol, `EnvSecretSource`, `SecretValue` with redacted `repr`/`str`, `resolve_secret` — no Vault/Secrets-Manager client, same "no backend chosen yet" reasoning as ADR-023's tracing deferral). `ops.validation` (`ValidationResult`, `validate_runtime`/`require_valid_runtime`, mirroring `ops.health`'s report/gate split). `ops.models.RuntimeContext{platform_info, environment, startup_time}` — deliberately narrower than the proposed shape: no `validated_config` field (a constructed `RuntimeContext` *is* the proof validation passed) and no duplicate `git_commit` (already on `platform_info`); never carries secret material itself. `build_runtime_context` composes validation, secret resolution, and optional health checks (empty by default) into the one startup sequence WP4 will invoke. |
| [025 — Deployment & Release Automation Design](ADR-025-Deployment-And-Release-Automation-Design.md) | Accepted | Milestone 12 WP4: `ops.models.DeploymentInfo{version, git_commit, build_time, deployment_environment, deployment_id, rollback_target}` — one deployment instance, distinct from `PlatformInfo` (the build). `ops.deployment` (`validate_deployment` checks a `DeploymentInfo` against a `RuntimeContext`; `ReleaseManifest`/`compute_checksum`/`verify_release_manifest` verify release-artifact SHA-256 checksums; both reuse `ops.validation.ValidationResult` rather than a bespoke result type). `ops.rollback.select_rollback_target` picks the last-known-good prior deployment from history — a separate module since it operates on a sequence, not one object. Deliberately deferred: literal Kubernetes manifests, a CI "deploy" job, and any release/rollback shell script — no deployment target has been chosen, same "no backend chosen yet" reasoning as ADR-023/ADR-024's tracing/secrets-backend deferrals. |

## When to write one

Write an ADR for a decision that is:

- **Significant** — it shapes how future code gets written, not a local
  implementation detail.
- **Hard to reverse** — changing it later means touching many call sites,
  not one function.
- **Non-obvious** — a reasonable engineer could have made a different
  choice, and the reasoning for this one isn't self-evident from the code.

Don't write one for routine implementation choices already covered by
[Standards/Coding Standards.md](../../Standards/Coding%20Standards.md) or
[Standards/Python Style Guide.md](../../Standards/Python%20Style%20Guide.md)
— those are the default; an ADR is for a deliberate departure from a
default, or a foundational choice those standards themselves rest on.

## Numbering and naming

`ADR-NNN-Short-Title.md`, zero-padded to three digits, numbered
**sequentially and never reused**, even if a later ADR supersedes an
earlier one. The initial convention is one ADR per milestone (matching
[PROJECT_STATUS.md](../../../../PROJECT_STATUS.md)'s numbering —
`ADR-001-Foundation.md` for Milestone 1, `ADR-002-Market-Data.md` for
Milestone 2, and so on), bundling every significant decision made during
that milestone into one record. A milestone with no significant
architectural decisions doesn't need an ADR just to keep the count
matching — the sequence only needs to stay monotonically increasing, not
gapless-and-1:1-with-milestones forever. If a decision significant enough
to warrant its own record comes up between milestones, give it the next
number regardless of milestone boundaries.

## Status lifecycle

Each ADR (and, since ADRs in this repo bundle multiple decisions, each
decision within one) carries a status:

| Status | Meaning |
|---|---|
| Proposed | Under discussion, not yet acted on |
| Accepted | Decided and reflected in the current codebase |
| Superseded by ADR-NNN | No longer current; the linked ADR replaces it |
| Deprecated | No longer current, with no direct replacement |

**Never edit or delete an accepted decision to reflect a later change of
mind.** Write a new ADR that supersedes it, and mark the old one
`Superseded by ADR-NNN`. The old ADR's reasoning is still valuable
historical context — it usually explains why the *original* choice looked
right at the time, which is exactly the information most likely to matter
the next time someone reconsiders it.

## Format

Use [TEMPLATE.md](TEMPLATE.md) for each decision. At minimum: Context
(what problem/tension prompted a choice), Decision (what was chosen,
stated plainly), Consequences (both the benefit and the accepted
trade-off — an ADR that lists no downside wasn't looking hard enough),
and Alternatives Considered (what else was on the table and why it lost).

## Relationship to the rest of the handbook

- [00_MASTER_CHARTER.md](../../00_MASTER_CHARTER.md) is *prescriptive* —
  the standards every decision must operate within.
- ADRs are *explanatory* — why a specific decision satisfies (or, rarely,
  deliberately deviates from and amends) those standards.
- [Architecture/Known Gaps.md](../Known%20Gaps.md) is *status* — what
  isn't built yet.
- [PROJECT_STATUS.md](../../../../PROJECT_STATUS.md) is *progress* — which
  milestone is done.

An ADR that reveals a standard needs to change updates the Master Charter
in the same change, per Definition of Done — it doesn't just sit here
contradicting it.
