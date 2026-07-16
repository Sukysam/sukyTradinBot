"""Composition root for the runtime -- builds services and injects
dependencies. Contains no business logic of its own: every decision
here is "which already-built thing goes where," never "what should
happen to a bar." See
docs/engineering-handbook/Architecture/ADR/ADR-027-Runtime-Market-Data-Loop-Design.md
and
docs/engineering-handbook/Architecture/ADR/ADR-031-Signal-Orchestration-Design.md.

Each `build_*_loop` function builds its own emitters and composes its
own `on_bar` callback directly against `build_market_data_loop` via
`app.pipeline.compose_pipeline`, rather than delegating to the
previous phase's `build_*_loop` and injecting a callback into it.
`MarketDataLoop.on_bar` is fixed at construction time (no public
setter), so a later phase can't "add a stage" to an already-built
loop -- each `build_*_loop` therefore builds the full stage list for
its own phase, using the small `_build_*_stage` helpers below so the
actual construction logic (which buffer, which health check) is still
defined in exactly one place, not duplicated per phase.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from alpaca.data.enums import DataFeed

from app.buffer import BarBuffer, FeatureVectorBuffer
from app.config import FeatureLoopConfig, MarketDataLoopConfig, RegimeLoopConfig
from app.exceptions import GitCommitUnavailableError
from app.features_loop import FeatureVectorEmitter
from app.orchestration_loop import (
    LearningDecisionProvider,
    NewsSignalProvider,
    OrchestrationEmitter,
)
from app.pipeline import compose_pipeline
from app.regime_loop import RegimeEmitter
from app.runtime import BarCallback, MarketDataLoop
from app.strategy_loop import StrategyEmitter
from common.config import Settings
from common.time import SystemClock
from features.registry import DEFAULT_REGISTRY
from hmm.service import RegimeService
from market_data.interfaces import HistoricalDataProvider
from market_data.models import Timeframe
from market_data.providers.alpaca_historical import AlpacaHistoricalProvider
from ops.checks import (
    feature_registry_check,
    hmm_model_check,
    market_data_check,
    strategy_registry_check,
)
from ops.interfaces import HealthCheck
from ops.models import RuntimeContext
from ops.secrets import EnvSecretSource
from ops.startup import build_runtime_context
from ops.validation import require_valid_runtime, validate_runtime
from orchestration.config import OrchestrationConfig
from orchestration.interfaces import ArbitrationPolicy
from strategy.config import StrategyEngineConfig
from strategy.registry import StrategyRegistry
from strategy.service import StrategyService

_REQUIRED_SECRETS = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")

# Bumped 0.1.0 -> 0.2.0 for Phase B (feature pipeline, ADR-028) -> 0.3.0
# for Phase C (regime detection, ADR-029) -> 0.4.0 for Phase D (strategy
# engine, ADR-030) -> 0.5.0 for Phase E (signal orchestration, ADR-031).
__version__ = "0.5.0"

# One day back avoids the free-tier "recent SIP data" restriction the
# probe would otherwise hit -- see ADR-027 and
# market_data.providers.alpaca_historical's module docstring.
_PROBE_LOOKBACK = timedelta(days=2)


def current_git_commit() -> str:
    """Best-effort `git rev-parse HEAD`. Raises `GitCommitUnavailableError`
    rather than silently returning a placeholder -- a `RuntimeContext`
    built with a fabricated commit hash is worse than one that fails
    loudly, matching `backtest.engine.current_git_commit`'s identical
    reasoning (duplicated here, not imported from `backtest`, so this
    runtime never pulls in `backtest`'s full strategy/risk/execution/
    hmm/features dependency chain just for a `subprocess.run` call)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise GitCommitUnavailableError(f"Could not determine git commit: {exc}") from exc
    return result.stdout.strip()


def _connectivity_probe(
    provider: HistoricalDataProvider, symbol: str, timeframe: Timeframe
) -> bool:
    """Confirms Alpaca is actually reachable with the configured
    credentials/feed -- queries a window safely in the past (never
    `now()`) so the probe itself never trips the free-tier "recent SIP
    data" restriction it exists to guard against."""
    end = datetime.now(timezone.utc) - timedelta(days=1)
    start = end - _PROBE_LOOKBACK
    try:
        provider.get_bars(symbol, start, end, timeframe)
    except Exception:
        return False
    return True


def _feature_registry_probe() -> bool:
    """The registry is populated as an import side effect of `import
    features` (see `features/__init__.py`) -- this only confirms that
    side effect actually ran and produced at least one feature, not
    that any particular feature is present."""
    return len(DEFAULT_REGISTRY) > 0


def _build_feature_stage(
    config: FeatureLoopConfig,
) -> tuple[FeatureVectorEmitter, list[HealthCheck]]:
    emitter = FeatureVectorEmitter(buffer=BarBuffer(max_bars=config.max_bars_per_symbol))
    checks: list[HealthCheck] = [feature_registry_check(_feature_registry_probe)]
    return emitter, checks


def _build_regime_stage(
    config: RegimeLoopConfig, regime_service: RegimeService
) -> tuple[RegimeEmitter, list[HealthCheck]]:
    emitter = RegimeEmitter(
        regime_service,
        buffer=FeatureVectorBuffer(max_vectors=config.max_feature_vectors_per_symbol),
    )
    checks: list[HealthCheck] = [hmm_model_check(lambda: regime_service.n_states > 0)]
    return emitter, checks


def _build_strategy_stage(
    strategy_registry: StrategyRegistry, strategy_config: StrategyEngineConfig | None
) -> tuple[StrategyEmitter, list[HealthCheck]]:
    service = StrategyService(strategy_registry, strategy_config)
    emitter = StrategyEmitter(service)
    checks: list[HealthCheck] = [
        strategy_registry_check(lambda: len(strategy_registry.names()) > 0)
    ]
    return emitter, checks


def build_market_data_loop(
    config: MarketDataLoopConfig,
    *,
    feed: DataFeed = DataFeed.IEX,
    provider: HistoricalDataProvider | None = None,
    on_bar: BarCallback | None = None,
    extra_checks: Sequence[HealthCheck] = (),
) -> tuple[MarketDataLoop, RuntimeContext]:
    """Validate startup configuration/credentials, then build a
    `MarketDataLoop` ready to `start()`.

    `provider` is injectable -- defaults to a real
    `AlpacaHistoricalProvider(feed=feed)`, but a test (or a later
    phase wanting a different provider) can supply its own, the same
    "always injectable, never hardcoded inside business logic"
    convention every other constructor in this codebase follows.

    `on_bar` and `extra_checks` are how every `build_*_loop` below
    extends this function without rewriting it -- typically `on_bar`
    is the result of `app.pipeline.compose_pipeline(...)`, not a
    single emitter's method directly, once more than one stage is
    involved.

    Raises `ops.exceptions.RuntimeValidationError` if `ALPACA_API_KEY`/
    `ALPACA_SECRET_KEY` aren't set, and `ops.exceptions.
    UnhealthyPlatformError` if any health check fails -- both before
    any loop iteration runs, per this platform's established "fail
    fast at startup, not on the first poll" convention
    (`ops.startup.build_runtime_context`).
    """
    environment = Settings().environment
    git_commit = current_git_commit()

    # Validate required secrets exist *before* constructing the default
    # `AlpacaHistoricalProvider` -- its own constructor would otherwise
    # discover a missing key itself and raise
    # `market_data.errors.ProviderAuthenticationError`, a less
    # informative failure than `ops.validation`'s "every missing secret
    # in one pass" report. Re-validated (cheap: a couple of env-var
    # reads) inside `build_runtime_context` below so this function has
    # exactly one place that produces the final `RuntimeContext`.
    require_valid_runtime(
        validate_runtime(
            environment=environment,
            required_secrets=_REQUIRED_SECRETS,
            secret_source=EnvSecretSource(),
        )
    )

    if provider is None:
        provider = AlpacaHistoricalProvider(feed=feed)

    checks = [
        market_data_check(
            lambda: _connectivity_probe(provider, config.symbols[0], config.timeframe)
        ),
        *extra_checks,
    ]

    runtime_context = build_runtime_context(
        version=__version__,
        git_commit=git_commit,
        environment=environment,
        required_secrets=_REQUIRED_SECRETS,
        checks=checks,
    )

    loop = MarketDataLoop(
        provider,
        symbols=config.symbols,
        timeframe=config.timeframe,
        poll_interval_seconds=config.poll_interval_seconds,
        lookback=config.lookback,
        clock=SystemClock(),
        on_bar=on_bar,
    )
    return loop, runtime_context


def build_feature_loop(
    config: FeatureLoopConfig,
    *,
    feed: DataFeed = DataFeed.IEX,
    provider: HistoricalDataProvider | None = None,
    extra_checks: Sequence[HealthCheck] = (),
) -> tuple[MarketDataLoop, RuntimeContext, FeatureVectorEmitter]:
    """Phase B composition root, standalone (just this phase). See
    `build_orchestration_loop` for the full A-E pipeline composed
    together.
    """
    emitter, checks = _build_feature_stage(config)
    loop, runtime_context = build_market_data_loop(
        config.market_data,
        feed=feed,
        provider=provider,
        on_bar=compose_pipeline(emitter.handle_bar),
        extra_checks=[*checks, *extra_checks],
    )
    return loop, runtime_context, emitter


def build_regime_loop(
    config: RegimeLoopConfig,
    regime_service: RegimeService,
    *,
    feed: DataFeed = DataFeed.IEX,
    provider: HistoricalDataProvider | None = None,
    extra_checks: Sequence[HealthCheck] = (),
) -> tuple[MarketDataLoop, RuntimeContext, FeatureVectorEmitter, RegimeEmitter]:
    """Phase C composition root, standalone (Phase A/B/C only). See
    `build_orchestration_loop` for the full A-E pipeline composed
    together.

    `regime_service` is a required, injected `RegimeService` -- there
    is no default construction here, unlike `provider`'s default
    `AlpacaHistoricalProvider`. This project has no trained/persisted
    HMM model artifact yet (`hmm.persistence.load` needs one on disk),
    so there is no equivalent "just needs an env var" default that
    would actually work; the caller must train or load a
    `RegimeService` itself. See ADR-029.
    """
    feature_emitter, feature_checks = _build_feature_stage(config.feature_loop)
    regime_emitter, regime_checks = _build_regime_stage(config, regime_service)
    loop, runtime_context = build_market_data_loop(
        config.feature_loop.market_data,
        feed=feed,
        provider=provider,
        on_bar=compose_pipeline(feature_emitter.handle_bar, regime_emitter.handle_frame),
        extra_checks=[*feature_checks, *regime_checks, *extra_checks],
    )
    return loop, runtime_context, feature_emitter, regime_emitter


def build_strategy_loop(
    config: RegimeLoopConfig,
    regime_service: RegimeService,
    strategy_registry: StrategyRegistry,
    *,
    strategy_config: StrategyEngineConfig | None = None,
    feed: DataFeed = DataFeed.IEX,
    provider: HistoricalDataProvider | None = None,
) -> tuple[MarketDataLoop, RuntimeContext, FeatureVectorEmitter, RegimeEmitter, StrategyEmitter]:
    """Phase D composition root, standalone (Phase A/B/C/D only). See
    `build_orchestration_loop` for the full A-E pipeline composed
    together.

    `strategy_registry` is a required, injected `StrategyRegistry` --
    the same reasoning as `regime_service` (ADR-029): which
    `regime_id`s map to which strategy style is inherently tied to a
    specific trained model's regime semantics (arbitrary MAP-state
    indices with no fixed meaning), which nobody has defined for any
    real model yet. Unlike `RegimeService`, `StrategyService` itself is
    cheap to construct (no training/persistence), so this function
    builds it internally from `strategy_registry`/`strategy_config`
    rather than asking the caller to hand over an already-built
    `StrategyService`. See ADR-030.
    """
    feature_emitter, feature_checks = _build_feature_stage(config.feature_loop)
    regime_emitter, regime_checks = _build_regime_stage(config, regime_service)
    strategy_emitter, strategy_checks = _build_strategy_stage(strategy_registry, strategy_config)
    loop, runtime_context = build_market_data_loop(
        config.feature_loop.market_data,
        feed=feed,
        provider=provider,
        on_bar=compose_pipeline(
            feature_emitter.handle_bar,
            regime_emitter.handle_frame,
            strategy_emitter.handle_frame,
        ),
        extra_checks=[*feature_checks, *regime_checks, *strategy_checks],
    )
    return loop, runtime_context, feature_emitter, regime_emitter, strategy_emitter


def build_orchestration_loop(
    config: RegimeLoopConfig,
    regime_service: RegimeService,
    strategy_registry: StrategyRegistry,
    *,
    strategy_config: StrategyEngineConfig | None = None,
    policy: ArbitrationPolicy | None = None,
    orchestration_config: OrchestrationConfig | None = None,
    learning_decision_provider: LearningDecisionProvider | None = None,
    news_signal_provider: NewsSignalProvider | None = None,
    feed: DataFeed = DataFeed.IEX,
    provider: HistoricalDataProvider | None = None,
) -> tuple[
    MarketDataLoop,
    RuntimeContext,
    FeatureVectorEmitter,
    RegimeEmitter,
    StrategyEmitter,
    OrchestrationEmitter,
]:
    """Phase E composition root -- the full A-E pipeline: `MarketDataLoop
    -> FeatureVectorEmitter -> RegimeEmitter -> StrategyEmitter ->
    OrchestrationEmitter`, composed into one `on_bar` callback via
    `app.pipeline.compose_pipeline`.

    `learning_decision_provider`/`news_signal_provider` default to
    `None`, meaning no advisory input -- there is no `MemoryEmitter`/
    `NlpEmitter` stage in this runtime by design (per direct
    instruction). `memory`/`nlp` were built shadow-mode-only
    (Milestones 9/10: never influences production); `arbitrate` already
    treats a missing advisory signal as the ordinary case, so this is
    the honest default, not a placeholder. See ADR-031.
    """
    feature_emitter, feature_checks = _build_feature_stage(config.feature_loop)
    regime_emitter, regime_checks = _build_regime_stage(config, regime_service)
    strategy_emitter, strategy_checks = _build_strategy_stage(strategy_registry, strategy_config)
    orchestration_emitter = OrchestrationEmitter(
        policy=policy,
        config=orchestration_config,
        learning_decision_provider=learning_decision_provider,
        news_signal_provider=news_signal_provider,
    )
    loop, runtime_context = build_market_data_loop(
        config.feature_loop.market_data,
        feed=feed,
        provider=provider,
        on_bar=compose_pipeline(
            feature_emitter.handle_bar,
            regime_emitter.handle_frame,
            strategy_emitter.handle_frame,
            orchestration_emitter.handle_frame,
        ),
        extra_checks=[*feature_checks, *regime_checks, *strategy_checks],
    )
    return (
        loop,
        runtime_context,
        feature_emitter,
        regime_emitter,
        strategy_emitter,
        orchestration_emitter,
    )


__all__ = [
    "build_feature_loop",
    "build_market_data_loop",
    "build_orchestration_loop",
    "build_regime_loop",
    "build_strategy_loop",
    "current_git_commit",
]
