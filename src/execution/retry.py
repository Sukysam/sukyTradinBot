"""Retry policy for broker submission -- the one place this concern lives
for the Execution Layer, per
[03_BACKEND_ENGINEER.md](../../docs/engineering-handbook/03_BACKEND_ENGINEER.md)'s
"one policy, one place" rule. Reuses `common.retry` rather than
reimplementing backoff.

`BrokerAdapter.submit_order` returns a `BrokerSubmissionResult`, it never
raises on an ordinary submission failure (see `broker_adapter.py`) --
`common.retry.call_with_retry` retries on *exceptions*, so
`submit_with_retry` bridges a failed result into
`TransientBrokerError` internally, retried, then translated back into a
`BrokerSubmissionResult` either way. Every retry resubmits the *same*
`OrderIntent.idempotency_key` as `client_order_id` -- the broker's own
idempotent handling of a repeated `client_order_id` is what actually
prevents a duplicate fill across retries, not anything in this module.
"""

from __future__ import annotations

from common.errors import RetryExhaustedError
from common.retry import RetryPolicy, call_with_retry
from execution.broker_adapter import BrokerSubmissionResult
from execution.exceptions import TransientBrokerError
from execution.interfaces import BrokerAdapter
from execution.models import OrderIntent

DEFAULT_BROKER_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    initial_delay_seconds=0.5,
    backoff_multiplier=2.0,
    exceptions=(TransientBrokerError,),
)


def submit_with_retry(
    adapter: BrokerAdapter,
    intent: OrderIntent,
    policy: RetryPolicy | None = None,
) -> BrokerSubmissionResult:
    active_policy = policy or DEFAULT_BROKER_RETRY_POLICY

    def _attempt() -> BrokerSubmissionResult:
        result = adapter.submit_order(intent)
        if not result.submitted:
            raise TransientBrokerError(result.error or "broker submission failed")
        return result

    try:
        return call_with_retry(_attempt, active_policy)
    except RetryExhaustedError as exc:
        return BrokerSubmissionResult(submitted=False, error=str(exc))


__all__ = ["DEFAULT_BROKER_RETRY_POLICY", "submit_with_retry"]
