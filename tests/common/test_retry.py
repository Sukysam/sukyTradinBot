from __future__ import annotations

import pytest

from common.errors import RetryExhaustedError
from common.retry import RetryPolicy, call_with_retry


def test_retry_policy_rejects_invalid_max_attempts() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)


def test_retry_policy_rejects_negative_initial_delay() -> None:
    with pytest.raises(ValueError, match="initial_delay_seconds"):
        RetryPolicy(initial_delay_seconds=-1)


def test_retry_policy_rejects_backoff_multiplier_below_one() -> None:
    with pytest.raises(ValueError, match="backoff_multiplier"):
        RetryPolicy(backoff_multiplier=0.5)


def test_delay_for_attempt_applies_exponential_backoff() -> None:
    policy = RetryPolicy(initial_delay_seconds=1.0, backoff_multiplier=2.0)
    assert policy.delay_for_attempt(1) == 1.0
    assert policy.delay_for_attempt(2) == 2.0
    assert policy.delay_for_attempt(3) == 4.0


def test_delay_for_attempt_rejects_attempt_below_one() -> None:
    policy = RetryPolicy()
    with pytest.raises(ValueError, match="attempt"):
        policy.delay_for_attempt(0)


def test_call_with_retry_returns_result_on_first_success() -> None:
    calls = []

    def succeeds() -> str:
        calls.append(1)
        return "ok"

    result = call_with_retry(succeeds, sleep=lambda _: None)

    assert result == "ok"
    assert len(calls) == 1


def test_call_with_retry_retries_then_succeeds() -> None:
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("transient")
        return "recovered"

    sleeps: list[float] = []
    result = call_with_retry(
        flaky,
        RetryPolicy(max_attempts=5, initial_delay_seconds=0.01),
        sleep=sleeps.append,
    )

    assert result == "recovered"
    assert attempts["count"] == 3
    assert len(sleeps) == 2  # slept before attempt 2 and attempt 3, not after final success


def test_call_with_retry_raises_retry_exhausted_after_max_attempts() -> None:
    def always_fails() -> str:
        raise ConnectionError("permanently down")

    with pytest.raises(RetryExhaustedError) as exc_info:
        call_with_retry(
            always_fails,
            RetryPolicy(max_attempts=3, initial_delay_seconds=0.0),
            sleep=lambda _: None,
        )

    assert "3 attempts" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ConnectionError)


def test_call_with_retry_only_retries_configured_exception_types() -> None:
    def raises_type_error() -> str:
        raise TypeError("not retryable per this policy")

    policy = RetryPolicy(max_attempts=3, exceptions=(ConnectionError,))

    with pytest.raises(TypeError):
        call_with_retry(raises_type_error, policy, sleep=lambda _: None)
