"""`RiskEmitter` -- Phase F: the stage after `OrchestrationEmitter` in
the composed pipeline, wired to `RiskService`. See
docs/engineering-handbook/Architecture/ADR/ADR-032-Runtime-Risk-Management-Design.md.

`handle_frame` bridges `FinalDecision` into `RiskService.decide`'s
`StrategyDecision`-shaped input (see `_effective_strategy_decision`
below -- this is the specific gap `orchestration/__init__.py`'s own
module docstring flagged as "not authorized by this milestone"; Phase
F is that authorization), calls `RiskService.decide`, logs one
structured event per computed `ExecutionDecision`, records it on an
`ops.metrics.MetricsRegistry`, and returns the enriched frame -- or
`None` on failure. A failure is caught and logged, never propagated,
matching every earlier emitter's failure-isolation convention. The
runtime stops here: no broker calls, no order submission -- Phase G is
a separate, later, explicitly authorized decision.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Callable

from app.frame import RuntimeFrame
from ops.metrics import MetricsRegistry
from risk.exceptions import RiskError
from risk.models import AccountState, PortfolioState
from risk.service import RiskService
from strategy.models import StrategyDecision

logger = logging.getLogger(__name__)

PortfolioStateProvider = Callable[[], PortfolioState]
AccountStateProvider = Callable[[], AccountState]


def _effective_strategy_decision(frame: RuntimeFrame) -> StrategyDecision:
    """`RiskService.decide` takes a `StrategyDecision`, not a
    `FinalDecision`, and `FinalDecision` has no `expected_holding_period`/
    `metadata` to build a full new `StrategyDecision` from scratch. Every
    field arbitration can actually change (`allocation`, `confidence`,
    and the human-readable `reasoning`) is overridden on the *original*
    `strategy_decision` the frame already carries; everything else
    (`timestamp`, `symbol`, `strategy_id`, `regime_id`,
    `expected_holding_period`, `metadata`) is unaffected by arbitration
    and is kept as-is. Using the pre-arbitration `strategy_decision`
    directly here instead would silently bypass Signal Orchestration's
    entire job -- `RiskService.decide` bounds `approved_allocation` to
    `[0.0, decision.allocation]`, so the ceiling it sizes against must
    be the *arbitrated* allocation, not the strategy's original ask.
    """
    strategy_decision = frame.require_strategy_decision()
    final_decision = frame.require_final_decision()
    return replace(
        strategy_decision,
        allocation=final_decision.final_allocation,
        confidence=final_decision.confidence,
        reasoning=final_decision.rationale,
    )


class RiskEmitter:
    """Wraps exactly one `RiskService`. Holds no "next stage" hook --
    see `app.pipeline.compose_pipeline` for how this is wired to
    whatever comes after it in a future phase.

    `portfolio_state_provider`/`account_state_provider` are required
    (no default) -- unlike Phase E's optional advisory providers,
    `RiskService.decide` has no graceful "no portfolio" path, and a
    single snapshot injected once at bootstrap would go stale
    immediately (portfolio/account state changes with every trade and
    every price move). Each is called fresh on every `handle_frame`.
    This runtime has no broker/account-query component yet (that's
    Phase G's job), so there is no real default to construct either --
    the same "no working default, caller must supply one" reasoning
    ADR-029/ADR-030 already established for `regime_service`/
    `strategy_registry`, applied here for a different underlying
    reason (live data, not a missing artifact).
    """

    def __init__(
        self,
        risk_service: RiskService,
        portfolio_state_provider: PortfolioStateProvider,
        account_state_provider: AccountStateProvider,
        *,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._service = risk_service
        self._portfolio_state_provider = portfolio_state_provider
        self._account_state_provider = account_state_provider
        self._metrics = metrics or MetricsRegistry()

    @property
    def metrics(self) -> MetricsRegistry:
        return self._metrics

    def handle_frame(self, frame: RuntimeFrame) -> RuntimeFrame | None:
        effective_decision = _effective_strategy_decision(frame)

        try:
            portfolio = self._portfolio_state_provider()
        except Exception as exc:
            self._metrics.counter(
                "execution_decision_errors_total",
                "Number of RiskEmitter attempts that failed (provider or RiskService).",
            ).inc()
            logger.warning(
                "portfolio_state_provider failed",
                extra={
                    "event": "portfolio_state_provider_failed",
                    "symbol": effective_decision.symbol,
                    "error": str(exc),
                },
            )
            return None

        try:
            account = self._account_state_provider()
        except Exception as exc:
            self._metrics.counter(
                "execution_decision_errors_total",
                "Number of RiskEmitter attempts that failed (provider or RiskService).",
            ).inc()
            logger.warning(
                "account_state_provider failed",
                extra={
                    "event": "account_state_provider_failed",
                    "symbol": effective_decision.symbol,
                    "error": str(exc),
                },
            )
            return None

        started_at = time.perf_counter()
        try:
            execution_decision = self._service.decide(effective_decision, portfolio, account)
        except RiskError as exc:
            self._metrics.counter(
                "execution_decision_errors_total",
                "Number of RiskEmitter attempts that failed (provider or RiskService).",
            ).inc()
            logger.warning(
                "execution decision failed",
                extra={
                    "event": "execution_decision_failed",
                    "symbol": effective_decision.symbol,
                    "error": str(exc),
                },
            )
            return None
        latency_seconds = time.perf_counter() - started_at

        self._metrics.counter(
            "execution_decisions_emitted_total",
            "Number of ExecutionDecisions successfully computed and emitted.",
        ).inc()
        self._metrics.gauge(
            "execution_decision_latency_seconds",
            "Latency of the most recent RiskService.decide call.",
        ).set(latency_seconds)

        logger.info(
            "execution decision emitted",
            extra={
                "event": "execution_decision_emitted",
                "symbol": execution_decision.symbol,
                "timestamp": execution_decision.timestamp.isoformat(),
                "approved": execution_decision.approved,
                "approved_allocation": execution_decision.approved_allocation,
                "decision_type": execution_decision.decision_type.value,
                "latency_seconds": latency_seconds,
            },
        )

        return frame.with_execution_decision(execution_decision)


__all__ = ["AccountStateProvider", "PortfolioStateProvider", "RiskEmitter"]
