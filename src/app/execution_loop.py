"""`ExecutionEmitter` and `BrokerSubmissionEmitter` -- Phase G: the last
two stages in the composed pipeline. See
docs/engineering-handbook/Architecture/ADR/ADR-033-Runtime-Paper-Execution-Design.md.

Deliberately split into two stages, per direct instruction:
`ExecutionEmitter` performs exactly one transformation
(`ExecutionDecision -> ExecutionService -> OrderIntent`, never touching
a broker); `BrokerSubmissionEmitter` is the only stage in this entire
runtime allowed to talk to a broker (`OrderIntent -> BrokerAdapter ->
BrokerSubmissionResult`). Keeping order *construction* separate from
order *submission* is what makes retries, simulation, and a future
paper/live switch straightforward -- a caller can swap or omit either
stage without touching the other.

This module ends the runtime. No fill handling, trade lifecycle
tracking, or memory/experience recording happens here or anywhere else
in this codebase yet -- those are explicitly future work, downstream of
a stable, observed submission path.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from app.frame import RuntimeFrame
from common.retry import RetryPolicy
from execution.exceptions import ExecutionError
from execution.execution_service import ExecutionService
from execution.interfaces import BrokerAdapter
from execution.retry import DEFAULT_BROKER_RETRY_POLICY, submit_with_retry
from ops.metrics import MetricsRegistry
from risk.models import PortfolioState

logger = logging.getLogger(__name__)

PortfolioStateProvider = Callable[[], PortfolioState]


class ExecutionEmitter:
    """Wraps exactly one `ExecutionService`. Never imports or calls a
    broker -- `execution/__init__.py`'s own module docstring is explicit
    that this package's `BrokerAdapter` is the only sanctioned way to
    submit an `OrderIntent`, and that submission is a separate concern
    from building one. Holds no "next stage" hook -- see
    `app.pipeline.compose_pipeline`.
    """

    def __init__(
        self,
        execution_service: ExecutionService,
        portfolio_state_provider: PortfolioStateProvider,
        *,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._service = execution_service
        self._portfolio_state_provider = portfolio_state_provider
        self._metrics = metrics or MetricsRegistry()

    @property
    def metrics(self) -> MetricsRegistry:
        return self._metrics

    def handle_frame(self, frame: RuntimeFrame) -> RuntimeFrame | None:
        execution_decision = frame.require_execution_decision()

        try:
            portfolio = self._portfolio_state_provider()
        except Exception as exc:
            self._metrics.counter(
                "order_intent_errors_total",
                "Number of ExecutionEmitter attempts that failed (provider or ExecutionService).",
            ).inc()
            logger.warning(
                "portfolio_state_provider failed",
                extra={
                    "event": "portfolio_state_provider_failed",
                    "symbol": execution_decision.symbol,
                    "error": str(exc),
                },
            )
            return None

        started_at = time.perf_counter()
        try:
            # `OrderBuilder.build` (called via `ExecutionService.decide`)
            # raises a bare `ValueError` for its own construction-time
            # checks (e.g. a degenerate stop-loss) -- not a subclass of
            # `ExecutionError`, unlike the rest of this package's own
            # error hierarchy. Both are caught here for the same reason:
            # neither represents a wiring bug worth crashing the loop
            # over.
            order_intent = self._service.decide(execution_decision, portfolio)
        except (ExecutionError, ValueError) as exc:
            self._metrics.counter(
                "order_intent_errors_total",
                "Number of ExecutionEmitter attempts that failed (provider or ExecutionService).",
            ).inc()
            logger.warning(
                "order intent failed",
                extra={
                    "event": "order_intent_failed",
                    "symbol": execution_decision.symbol,
                    "error": str(exc),
                },
            )
            return None
        latency_seconds = time.perf_counter() - started_at

        if order_intent is None:
            # An ordinary, expected outcome -- `execution_decision` was
            # not approved (rejected or fully suppressed by Risk), so
            # there is nothing to submit. Not a failure: no counter, no
            # warning, just an informational log and the end of this
            # frame's journey.
            logger.info(
                "order intent not built",
                extra={
                    "event": "order_intent_not_built",
                    "symbol": execution_decision.symbol,
                    "approved": execution_decision.approved,
                },
            )
            return None

        self._metrics.counter(
            "order_intents_emitted_total",
            "Number of OrderIntents successfully built and emitted.",
        ).inc()
        self._metrics.gauge(
            "order_intent_latency_seconds",
            "Latency of the most recent ExecutionService.decide call.",
        ).set(latency_seconds)

        logger.info(
            "order intent emitted",
            extra={
                "event": "order_intent_emitted",
                "symbol": order_intent.symbol,
                "timestamp": order_intent.timestamp.isoformat(),
                "side": order_intent.side.value,
                "quantity": order_intent.quantity,
                "order_type": order_intent.order_type.value,
                "idempotency_key": order_intent.idempotency_key,
                "latency_seconds": latency_seconds,
            },
        )

        return frame.with_order_intent(order_intent)


class BrokerSubmissionEmitter:
    """The only stage in this runtime allowed to talk to a broker.
    Submits via `execution.retry.submit_with_retry` (the package's own
    sanctioned, already-built retry mechanism -- three attempts with
    backoff by default, resubmitting the same `idempotency_key` each
    time so the broker's own idempotent handling prevents a duplicate
    fill across retries), never calls `broker_adapter.submit_order`
    directly. Holds no "next stage" hook -- this is the last stage in
    the pipeline today.
    """

    def __init__(
        self,
        broker_adapter: BrokerAdapter,
        *,
        retry_policy: RetryPolicy = DEFAULT_BROKER_RETRY_POLICY,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._broker_adapter = broker_adapter
        self._retry_policy = retry_policy
        self._metrics = metrics or MetricsRegistry()

    @property
    def metrics(self) -> MetricsRegistry:
        return self._metrics

    def handle_frame(self, frame: RuntimeFrame) -> RuntimeFrame | None:
        order_intent = frame.require_order_intent()

        started_at = time.perf_counter()
        try:
            result = submit_with_retry(self._broker_adapter, order_intent, self._retry_policy)
        except Exception as exc:
            # `submit_with_retry` is documented to never raise (a
            # `RetryExhaustedError` is caught internally and translated
            # into `BrokerSubmissionResult(submitted=False, ...)`) --
            # this is a last-resort safety net for a genuinely
            # unexpected failure in the adapter or retry plumbing
            # itself, not an expected code path.
            self._metrics.counter(
                "broker_submission_errors_total",
                "Number of submit_with_retry calls that raised unexpectedly.",
            ).inc()
            logger.error(
                "broker submission raised unexpectedly",
                extra={
                    "event": "broker_submission_raised",
                    "symbol": order_intent.symbol,
                    "error": str(exc),
                },
            )
            return None
        latency_seconds = time.perf_counter() - started_at

        if result.submitted:
            self._metrics.counter(
                "broker_submissions_accepted_total",
                "Number of OrderIntents the broker accepted.",
            ).inc()
            logger.info(
                "broker submission accepted",
                extra={
                    "event": "broker_submission_accepted",
                    "symbol": order_intent.symbol,
                    "broker_order_id": result.broker_order_id,
                    "latency_seconds": latency_seconds,
                },
            )
        else:
            self._metrics.counter(
                "broker_submissions_rejected_total",
                "Number of OrderIntents the broker rejected (after retry).",
            ).inc()
            logger.warning(
                "broker submission rejected",
                extra={
                    "event": "broker_submission_rejected",
                    "symbol": order_intent.symbol,
                    "error": result.error,
                    "latency_seconds": latency_seconds,
                },
            )
        self._metrics.gauge(
            "broker_submission_latency_seconds",
            "Latency of the most recent submit_with_retry call.",
        ).set(latency_seconds)

        # Enriched either way -- both "accepted" and "rejected" are
        # legitimate completed-stage outcomes the frame should carry,
        # distinct from this stage itself failing outright (`None`).
        return frame.with_broker_submission_result(result)


__all__ = ["BrokerSubmissionEmitter", "ExecutionEmitter", "PortfolioStateProvider"]
