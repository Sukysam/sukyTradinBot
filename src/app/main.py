"""Process entrypoint: `python -m app`. Builds the Phase B runtime
(`MarketDataLoop` -> `FeatureVectorEmitter` -> `FeatureVector`), starts
it, and stops it cleanly on SIGINT/SIGTERM. No business logic -- see
`app.bootstrap` for composition, `app.runtime`/`app.features_loop` for
the loop and feature computation themselves.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import timedelta

from app.bootstrap import build_feature_loop
from app.config import FeatureLoopConfig, MarketDataLoopConfig
from common.logging import configure_logging
from market_data.models import Timeframe

logger = logging.getLogger(__name__)

# Placeholder defaults for Phase B -- a dedicated config source (env
# vars, config/*.yaml) is deferred to a later phase; see ADR-027's
# Alternatives Considered.
_DEFAULT_CONFIG = FeatureLoopConfig(
    market_data=MarketDataLoopConfig(
        symbols=("AAPL",),
        timeframe=Timeframe.DAY_1,
        poll_interval_seconds=300.0,
        lookback=timedelta(days=5),
    ),
)


async def _run() -> None:
    configure_logging()
    loop, runtime_context, _emitter = build_feature_loop(_DEFAULT_CONFIG)
    logger.info(
        "market data loop starting",
        extra={
            "event": "loop_starting",
            "environment": runtime_context.environment,
            "version": runtime_context.platform_info.version,
            "git_commit": runtime_context.platform_info.git_commit,
            "symbols": list(_DEFAULT_CONFIG.market_data.symbols),
        },
    )

    running_loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        running_loop.add_signal_handler(sig, _request_stop)

    task = asyncio.create_task(loop.start())
    await stop_event.wait()

    logger.info("market data loop stopping", extra={"event": "loop_stopping"})
    await loop.stop()
    await task
    logger.info("market data loop stopped", extra={"event": "loop_stopped"})


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
