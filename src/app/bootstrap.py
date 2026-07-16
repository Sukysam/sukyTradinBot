"""Composition root for the runtime -- builds services and injects
dependencies. Contains no business logic of its own: every decision
here is "which already-built thing goes where," never "what should
happen to a bar." See
docs/engineering-handbook/Architecture/ADR/ADR-027-Runtime-Market-Data-Loop-Design.md.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from alpaca.data.enums import DataFeed

from app.buffer import BarBuffer, FeatureVectorBuffer
from app.config import FeatureLoopConfig, MarketDataLoopConfig, RegimeLoopConfig
from app.exceptions import GitCommitUnavailableError
from app.features_loop import FeatureVectorCallback, FeatureVectorEmitter
from app.regime_loop import RegimeEmitter
from app.runtime import BarCallback, MarketDataLoop
from common.config import Settings
from common.time import SystemClock
from features.registry import DEFAULT_REGISTRY
from hmm.service import RegimeService
from market_data.interfaces import HistoricalDataProvider
from market_data.models import Timeframe
from market_data.providers.alpaca_historical import AlpacaHistoricalProvider
from ops.checks import feature_registry_check, hmm_model_check, market_data_check
from ops.interfaces import HealthCheck
from ops.models import RuntimeContext
from ops.secrets import EnvSecretSource
from ops.startup import build_runtime_context
from ops.validation import require_valid_runtime, validate_runtime

_REQUIRED_SECRETS = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")

# Bumped 0.1.0 -> 0.2.0 for Phase B (feature pipeline, ADR-028) -> 0.3.0
# for Phase C (regime detection, ADR-029).
__version__ = "0.3.0"

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
    `AlpacaHistoricalProvider(feed=feed)`, but a test (or a future
    phase wanting a different provider) can supply its own, the same
    "always injectable, never hardcoded inside business logic"
    convention every other constructor in this codebase follows
    (`AlpacaHistoricalProvider.__init__`'s own `bars_client` parameter
    included).

    `on_bar` and `extra_checks` are how a later phase extends this
    function without rewriting it -- see `build_feature_loop` below,
    which passes `on_bar=emitter.handle_bar` and
    `extra_checks=[feature_registry_check(...)]`.

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

    # `market_data_check` plus whatever `extra_checks` the caller adds
    # for subsystems it wires in -- the other `ops.checks` factories
    # (HMM model, risk service, ...) still describe subsystems no code
    # path in this runtime reaches yet, so they stay excluded here.
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
    on_feature_vector: FeatureVectorCallback | None = None,
    extra_checks: Sequence[HealthCheck] = (),
) -> tuple[MarketDataLoop, RuntimeContext, FeatureVectorEmitter]:
    """Phase B composition root. Builds a `FeatureVectorEmitter` first,
    then delegates every Phase A concern -- secret validation,
    connectivity probe, `MarketDataLoop` construction -- to
    `build_market_data_loop`, wiring `emitter.handle_bar` in as
    `on_bar` and `feature_registry_check` in as an extra health check.
    No composition logic is duplicated between phases; see ADR-028.

    `on_feature_vector` and `extra_checks` are how a later phase
    extends this function without rewriting it, the same additive
    pattern `build_market_data_loop`'s own `on_bar`/`extra_checks`
    established for Phase B -- see `build_regime_loop` below.
    """
    emitter = FeatureVectorEmitter(
        buffer=BarBuffer(max_bars=config.max_bars_per_symbol),
        on_feature_vector=on_feature_vector,
    )
    loop, runtime_context = build_market_data_loop(
        config.market_data,
        feed=feed,
        provider=provider,
        on_bar=emitter.handle_bar,
        extra_checks=[feature_registry_check(_feature_registry_probe), *extra_checks],
    )
    return loop, runtime_context, emitter


def build_regime_loop(
    config: RegimeLoopConfig,
    regime_service: RegimeService,
    *,
    feed: DataFeed = DataFeed.IEX,
    provider: HistoricalDataProvider | None = None,
) -> tuple[MarketDataLoop, RuntimeContext, FeatureVectorEmitter, RegimeEmitter]:
    """Phase C composition root. Builds a `RegimeEmitter` first, then
    delegates every Phase A/B concern to `build_feature_loop`, wiring
    `regime_emitter.handle_feature_vector` in as `on_feature_vector`
    and `hmm_model_check` in as an extra health check.

    `regime_service` is a required, injected `RegimeService` -- there
    is no default construction here, unlike `provider`'s default
    `AlpacaHistoricalProvider`. This project has no trained/persisted
    HMM model artifact yet (`hmm.persistence.load` needs one on disk),
    so there is no equivalent "just needs an env var" default that
    would actually work; the caller must train or load a
    `RegimeService` itself. See ADR-029.
    """
    regime_emitter = RegimeEmitter(
        regime_service,
        buffer=FeatureVectorBuffer(max_vectors=config.max_feature_vectors_per_symbol),
    )
    loop, runtime_context, feature_emitter = build_feature_loop(
        config.feature_loop,
        feed=feed,
        provider=provider,
        on_feature_vector=regime_emitter.handle_feature_vector,
        extra_checks=[hmm_model_check(lambda: regime_service.n_states > 0)],
    )
    return loop, runtime_context, feature_emitter, regime_emitter


__all__ = [
    "build_feature_loop",
    "build_market_data_loop",
    "build_regime_loop",
    "current_git_commit",
]
