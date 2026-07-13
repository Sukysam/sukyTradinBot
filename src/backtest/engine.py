"""`BacktestEngine` -- Phase B: layers metrics and `ReplayRun`
reproducibility metadata on top of Phase A's `replay.run_replay`,
producing the frozen `BacktestResult` (ADR-014).

`git_commit` is a required, explicit parameter rather than something this
module shells out to `git` for internally -- per
[Coding Standards](../../docs/engineering-handbook/Standards/Coding%20Standards.md)'s
"dependency injection over hidden construction," an engine computing
performance metrics has no business also owning a subprocess call.
`current_git_commit()` below is an opt-in helper a caller can use to
supply one, kept separate so it's never invoked implicitly.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import backtest
import execution
import features.pipeline
import hmm
import risk
import strategy
from backtest.config import BacktestConfig
from backtest.exceptions import BacktestError
from backtest.interfaces import FillModel
from backtest.metrics import compute_metrics
from backtest.models import BacktestResult, ReplayRun
from backtest.replay import run_replay
from common.interfaces import Clock
from common.time import SystemClock
from hmm.service import RegimeService
from market_data.models import Bar
from risk.service import RiskService
from strategy.service import StrategyService


def current_git_commit() -> str:
    """Best-effort `git rev-parse HEAD` -- not called by `BacktestEngine`
    itself; callers opt in explicitly. Raises `BacktestError` rather than
    silently returning a placeholder if `git` isn't available, since a
    `ReplayRun` with a fabricated commit hash is worse than one that
    fails loudly."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BacktestError(
            f"could not determine git_commit via 'git rev-parse HEAD': {exc}"
        ) from exc
    return result.stdout.strip()


@dataclass(frozen=True)
class BacktestEngine:
    clock: Clock = field(default_factory=SystemClock)

    def run(
        self,
        config: BacktestConfig,
        bars: Mapping[str, Sequence[Bar]],
        regime_services: Mapping[str, RegimeService],
        strategy_service: StrategyService,
        risk_service: RiskService,
        *,
        run_id: str,
        git_commit: str,
        fill_model: FillModel | None = None,
    ) -> BacktestResult:
        replay_result = run_replay(
            config, bars, regime_services, strategy_service, risk_service, fill_model
        )

        metrics = compute_metrics(
            equity_curve=replay_result.equity_curve,
            trade_log=replay_result.trade_log,
            initial_equity=config.initial_equity,
            start_date=config.start_date,
            end_date=config.end_date,
        )

        pipeline_versions = {
            "backtest": backtest.__version__,
            "features": features.pipeline.PIPELINE_VERSION,
            "hmm": hmm.__version__,
            "strategy": strategy.__version__,
            "risk": risk.__version__,
            "execution": execution.__version__,
            **{
                f"hmm_model_{symbol}": service.model_version
                for symbol, service in regime_services.items()
            },
        }
        replay_run = ReplayRun(
            run_id=run_id,
            dataset=config.dataset,
            pipeline_versions=pipeline_versions,
            git_commit=git_commit,
            timestamp=self.clock.now(),
        )

        final_equity = replay_result.equity_curve[-1].equity

        return BacktestResult(
            start_date=config.start_date,
            end_date=config.end_date,
            symbols=config.symbols,
            initial_equity=config.initial_equity,
            final_equity=final_equity,
            trade_log=replay_result.trade_log,
            equity_curve=replay_result.equity_curve,
            replay_run=replay_run,
            generated_at=self.clock.now(),
            metadata={},
            **metrics,
        )


__all__ = ["BacktestEngine", "current_git_commit"]
