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

import logging
import subprocess
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from alpaca.data.enums import DataFeed
from alpaca.trading.client import TradingClient

from app.buffer import BarBuffer, FeatureVectorBuffer
from app.config import FeatureLoopConfig, MarketDataLoopConfig, RegimeLoopConfig
from app.exceptions import GitCommitUnavailableError
from app.execution_loop import BrokerSubmissionEmitter, ExecutionEmitter
from app.features_loop import FeatureVectorEmitter
from app.orchestration_loop import (
    LearningDecisionProvider,
    NewsSignalProvider,
    OrchestrationEmitter,
)
from app.pipeline import PipelineResult, ResultSink, compose_pipeline
from app.regime_loop import RegimeEmitter
from app.risk_loop import AccountStateProvider, PortfolioStateProvider, RiskEmitter
from app.runtime import BarCallback, MarketDataLoop
from app.strategy_loop import StrategyEmitter
from common.config import Settings
from common.retry import RetryPolicy
from common.time import SystemClock
from execution.broker_adapter import AlpacaBrokerAdapter
from execution.config import ExecutionServiceConfig
from execution.execution_service import ExecutionService
from execution.interfaces import BrokerAdapter
from execution.retry import DEFAULT_BROKER_RETRY_POLICY
from features.registry import DEFAULT_REGISTRY
from hmm.service import RegimeService
from market_data.auth import load_alpaca_credentials
from market_data.interfaces import HistoricalDataProvider
from market_data.models import Timeframe
from market_data.providers.alpaca_historical import AlpacaHistoricalProvider
from ops.checks import (
    execution_adapter_check,
    feature_registry_check,
    hmm_model_check,
    market_data_check,
    risk_service_check,
    strategy_registry_check,
)
from ops.interfaces import HealthCheck
from ops.models import RuntimeContext
from ops.secrets import EnvSecretSource
from ops.startup import build_runtime_context
from ops.validation import require_valid_runtime, validate_runtime
from orchestration.config import OrchestrationConfig
from orchestration.interfaces import ArbitrationPolicy
from risk.service import RiskService
from strategy.config import StrategyEngineConfig
from strategy.registry import StrategyRegistry
from strategy.service import StrategyService

logger = logging.getLogger(__name__)

_REQUIRED_SECRETS = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")

# Bumped 0.1.0 -> 0.2.0 for Phase B (feature pipeline, ADR-028) -> 0.3.0
# for Phase C (regime detection, ADR-029) -> 0.4.0 for Phase D (strategy
# engine, ADR-030) -> 0.5.0 for Phase E (signal orchestration, ADR-031)
# -> 0.6.0 for Phase F (risk management, ADR-032) -> 0.7.0 for Phase G
# (paper execution, ADR-033).
__version__ = "0.7.0"

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


def _build_orchestration_stage(
    *,
    policy: ArbitrationPolicy | None,
    config: OrchestrationConfig | None,
    learning_decision_provider: LearningDecisionProvider | None,
    news_signal_provider: NewsSignalProvider | None,
) -> tuple[OrchestrationEmitter, list[HealthCheck]]:
    emitter = OrchestrationEmitter(
        policy=policy,
        config=config,
        learning_decision_provider=learning_decision_provider,
        news_signal_provider=news_signal_provider,
    )
    # No health check: arbitration has no persisted resource or external
    # dependency of its own to sanity-check -- `policy` is either the
    # always-available default `SafetyFirstPolicy` or a caller-supplied,
    # already-constructed object.
    return emitter, []


def _build_risk_stage(
    risk_service: RiskService | None,
    portfolio_state_provider: PortfolioStateProvider,
    account_state_provider: AccountStateProvider,
) -> tuple[RiskEmitter, list[HealthCheck]]:
    service = risk_service or RiskService.default()
    emitter = RiskEmitter(service, portfolio_state_provider, account_state_provider)
    checks: list[HealthCheck] = [risk_service_check(lambda: len(service.validators) > 0)]
    return emitter, checks


def _default_broker_adapter() -> AlpacaBrokerAdapter:
    """Constructs the default `AlpacaBrokerAdapter`, reusing
    `market_data.auth.AlpacaCredentials.paper` (Milestone 2) rather than
    inventing a second, potentially-divergent paper/live flag --
    `credentials.paper` already defaults to `True` via the `ALPACA_PAPER`
    env var, so an unset value never silently means live trading. Client
    construction and credential handling belong here, not inside
    `execution.broker_adapter`, per that module's own documented design.
    """
    credentials = load_alpaca_credentials()
    trading_client = TradingClient(
        api_key=credentials.api_key,
        secret_key=credentials.secret_key,
        paper=credentials.paper,
    )
    if not credentials.paper:
        logger.warning(
            "LIVE TRADING ENABLED -- ALPACA_PAPER is not true. Orders "
            "submitted by this runtime will be REAL.",
            extra={"event": "live_trading_enabled"},
        )
    return AlpacaBrokerAdapter(trading_client)


def _build_execution_stage(
    historical_provider: HistoricalDataProvider,
    execution_service: ExecutionService | None,
    execution_config: ExecutionServiceConfig | None,
    portfolio_state_provider: PortfolioStateProvider,
) -> tuple[ExecutionEmitter, list[HealthCheck]]:
    service = execution_service or ExecutionService.default(historical_provider, execution_config)
    emitter = ExecutionEmitter(service, portfolio_state_provider)
    return emitter, []


def _build_broker_submission_stage(
    broker_adapter: BrokerAdapter | None,
    retry_policy: RetryPolicy,
) -> tuple[BrokerSubmissionEmitter, list[HealthCheck]]:
    adapter = broker_adapter or _default_broker_adapter()
    emitter = BrokerSubmissionEmitter(adapter, retry_policy=retry_policy)
    checks: list[HealthCheck] = [execution_adapter_check(lambda: adapter is not None)]
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
    orchestration_emitter, orchestration_checks = _build_orchestration_stage(
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
        extra_checks=[*feature_checks, *regime_checks, *strategy_checks, *orchestration_checks],
    )
    return (
        loop,
        runtime_context,
        feature_emitter,
        regime_emitter,
        strategy_emitter,
        orchestration_emitter,
    )


def build_risk_loop(
    config: RegimeLoopConfig,
    regime_service: RegimeService,
    strategy_registry: StrategyRegistry,
    portfolio_state_provider: PortfolioStateProvider,
    account_state_provider: AccountStateProvider,
    *,
    risk_service: RiskService | None = None,
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
    RiskEmitter,
]:
    """Phase F composition root -- the full A-F pipeline: `MarketDataLoop
    -> FeatureVectorEmitter -> RegimeEmitter -> StrategyEmitter ->
    OrchestrationEmitter -> RiskEmitter`, composed into one `on_bar`
    callback via `app.pipeline.compose_pipeline`. The runtime stops at
    `ExecutionDecision` -- no broker calls, no order submission; Phase G
    is a separate, later, explicitly authorized decision.

    `risk_service` defaults to `RiskService.default()` if not given --
    unlike `regime_service`/`strategy_registry`, a sensible default risk
    pipeline (`BuyingPowerValidator` + `ExposureCapacitySizing` +
    `DrawdownCircuitBreaker`) needs no trained model or per-model
    domain mapping to be meaningful; see `RiskService.default`'s own
    docstring. `portfolio_state_provider`/`account_state_provider`
    remain required, with no default -- portfolio/account state is
    live, per-account data this runtime has no broker-query component
    to fetch yet (that's Phase G's job). See ADR-032.
    """
    feature_emitter, feature_checks = _build_feature_stage(config.feature_loop)
    regime_emitter, regime_checks = _build_regime_stage(config, regime_service)
    strategy_emitter, strategy_checks = _build_strategy_stage(strategy_registry, strategy_config)
    orchestration_emitter, orchestration_checks = _build_orchestration_stage(
        policy=policy,
        config=orchestration_config,
        learning_decision_provider=learning_decision_provider,
        news_signal_provider=news_signal_provider,
    )
    risk_emitter, risk_checks = _build_risk_stage(
        risk_service, portfolio_state_provider, account_state_provider
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
            risk_emitter.handle_frame,
        ),
        extra_checks=[
            *feature_checks,
            *regime_checks,
            *strategy_checks,
            *orchestration_checks,
            *risk_checks,
        ],
    )
    return (
        loop,
        runtime_context,
        feature_emitter,
        regime_emitter,
        strategy_emitter,
        orchestration_emitter,
        risk_emitter,
    )


_EXECUTION_PIPELINE_STAGE_NAMES = (
    "feature",
    "regime",
    "strategy",
    "orchestration",
    "risk",
    "execution",
    "broker_submission",
)


def _log_pipeline_result(result: PipelineResult) -> None:
    """Default `on_result` sink for `build_execution_loop` -- a terminal,
    one-event-per-bar summary of how far the pipeline got, distinct from
    (and in addition to) each stage's own per-stage structured logging.
    Overridable via `build_execution_loop`'s own `on_result` parameter,
    same DI convention as every other dependency in this module.
    """
    symbol = result.frame.bar.symbol if result.frame is not None else None
    if result.error is not None:
        logger.warning(
            "pipeline stage raised",
            extra={
                "event": "pipeline_stage_raised",
                "completed_stage": result.completed_stage,
                "symbol": symbol,
                "error": result.error,
            },
        )
        return
    logger.info(
        "pipeline result",
        extra={
            "event": "pipeline_completed" if result.success else "pipeline_stopped",
            "completed_stage": result.completed_stage,
            "symbol": symbol,
            "success": result.success,
        },
    )


def build_execution_loop(
    config: RegimeLoopConfig,
    regime_service: RegimeService,
    strategy_registry: StrategyRegistry,
    portfolio_state_provider: PortfolioStateProvider,
    account_state_provider: AccountStateProvider,
    *,
    risk_service: RiskService | None = None,
    strategy_config: StrategyEngineConfig | None = None,
    policy: ArbitrationPolicy | None = None,
    orchestration_config: OrchestrationConfig | None = None,
    learning_decision_provider: LearningDecisionProvider | None = None,
    news_signal_provider: NewsSignalProvider | None = None,
    execution_service: ExecutionService | None = None,
    execution_config: ExecutionServiceConfig | None = None,
    broker_adapter: BrokerAdapter | None = None,
    broker_retry_policy: RetryPolicy = DEFAULT_BROKER_RETRY_POLICY,
    on_result: ResultSink | None = None,
    feed: DataFeed = DataFeed.IEX,
    provider: HistoricalDataProvider | None = None,
) -> tuple[
    MarketDataLoop,
    RuntimeContext,
    FeatureVectorEmitter,
    RegimeEmitter,
    StrategyEmitter,
    OrchestrationEmitter,
    RiskEmitter,
    ExecutionEmitter,
    BrokerSubmissionEmitter,
]:
    """Phase G composition root -- the full A-G pipeline: `MarketDataLoop
    -> FeatureVectorEmitter -> RegimeEmitter -> StrategyEmitter ->
    OrchestrationEmitter -> RiskEmitter -> ExecutionEmitter ->
    BrokerSubmissionEmitter`, composed into one `on_bar` callback via
    `app.pipeline.compose_pipeline`. This is the final phase of the
    runtime build: the pipeline now runs end-to-end from a bare `Bar`
    to a submitted (or rejected) order. No fill handling, trade
    lifecycle tracking, position reconciliation, or memory/experience
    recording happens here -- all explicitly deferred, future work. See
    ADR-033.

    `execution_service` defaults to `ExecutionService.default(...)`,
    built from the SAME resolved `HistoricalDataProvider` this function
    passes to `build_market_data_loop`, rather than each independently
    constructing its own -- avoiding two independent rate limiters/retry
    policies against the same Alpaca account. Secrets are validated
    explicitly, up front, before that default provider (or the default
    broker adapter, see `_default_broker_adapter`) is constructed --
    mirroring `build_market_data_loop`'s own validation, which would
    otherwise run too late to prevent a less-informative provider-level
    credential error.

    `broker_adapter` defaults to a real `AlpacaBrokerAdapter`, built
    from `market_data.auth.AlpacaCredentials.paper` -- which itself
    already defaults to `True` via the `ALPACA_PAPER` env var (Milestone
    2) -- so this runtime is paper-safe by default with no new flag to
    misconfigure; enabling live trading requires an explicit
    `ALPACA_PAPER=false` in the environment, never a code change here.

    `on_result`, if given, receives one `app.pipeline.PipelineResult`
    per bar processed -- which named stage the run reached and whether
    it succeeded, wrapping (not replacing) the `RuntimeFrame` itself.
    Defaults to `_log_pipeline_result`, a terminal, one-event-per-bar
    structured log distinct from each stage's own per-stage logging;
    this is this runtime's only pipeline composed with named stages and
    a result sink at all -- every earlier `build_*_loop` still composes
    with `compose_pipeline`'s bare positional-args form, unchanged.
    """
    environment = Settings().environment
    require_valid_runtime(
        validate_runtime(
            environment=environment,
            required_secrets=_REQUIRED_SECRETS,
            secret_source=EnvSecretSource(),
        )
    )
    resolved_provider = provider or AlpacaHistoricalProvider(feed=feed)

    feature_emitter, feature_checks = _build_feature_stage(config.feature_loop)
    regime_emitter, regime_checks = _build_regime_stage(config, regime_service)
    strategy_emitter, strategy_checks = _build_strategy_stage(strategy_registry, strategy_config)
    orchestration_emitter, orchestration_checks = _build_orchestration_stage(
        policy=policy,
        config=orchestration_config,
        learning_decision_provider=learning_decision_provider,
        news_signal_provider=news_signal_provider,
    )
    risk_emitter, risk_checks = _build_risk_stage(
        risk_service, portfolio_state_provider, account_state_provider
    )
    execution_emitter, execution_checks = _build_execution_stage(
        resolved_provider, execution_service, execution_config, portfolio_state_provider
    )
    broker_emitter, broker_checks = _build_broker_submission_stage(
        broker_adapter, broker_retry_policy
    )
    loop, runtime_context = build_market_data_loop(
        config.feature_loop.market_data,
        feed=feed,
        provider=resolved_provider,
        on_bar=compose_pipeline(
            feature_emitter.handle_bar,
            regime_emitter.handle_frame,
            strategy_emitter.handle_frame,
            orchestration_emitter.handle_frame,
            risk_emitter.handle_frame,
            execution_emitter.handle_frame,
            broker_emitter.handle_frame,
            stage_names=_EXECUTION_PIPELINE_STAGE_NAMES,
            on_result=on_result or _log_pipeline_result,
        ),
        extra_checks=[
            *feature_checks,
            *regime_checks,
            *strategy_checks,
            *orchestration_checks,
            *risk_checks,
            *execution_checks,
            *broker_checks,
        ],
    )
    return (
        loop,
        runtime_context,
        feature_emitter,
        regime_emitter,
        strategy_emitter,
        orchestration_emitter,
        risk_emitter,
        execution_emitter,
        broker_emitter,
    )


__all__ = [
    "build_execution_loop",
    "build_feature_loop",
    "build_market_data_loop",
    "build_orchestration_loop",
    "build_regime_loop",
    "build_risk_loop",
    "build_strategy_loop",
    "current_git_commit",
]
