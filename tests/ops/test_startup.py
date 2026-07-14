"""Tests for `ops.startup.build_runtime_context`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common.time import FixedClock
from ops.checks import configuration_check
from ops.exceptions import RuntimeValidationError, UnhealthyPlatformError
from ops.startup import build_runtime_context

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


class _FakeSecretSource:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, name: str) -> str | None:
        return self._values.get(name)


class TestBuildRuntimeContext:
    def test_builds_context_with_no_secrets_or_checks(self) -> None:
        context = build_runtime_context(
            version="0.12.0",
            git_commit="abc1234",
            environment="production",
            secret_source=_FakeSecretSource({}),
            clock=FixedClock(T0),
        )
        assert context.environment == "production"
        assert context.platform_info.version == "0.12.0"
        assert context.platform_info.git_commit == "abc1234"
        assert context.startup_time == T0

    def test_uses_explicit_python_version_when_given(self) -> None:
        context = build_runtime_context(
            version="0.12.0",
            git_commit="abc1234",
            environment="production",
            secret_source=_FakeSecretSource({}),
            python_version="3.99.0",
            clock=FixedClock(T0),
        )
        assert context.platform_info.python_version == "3.99.0"

    def test_defaults_python_version_from_platform_module(self) -> None:
        context = build_runtime_context(
            version="0.12.0",
            git_commit="abc1234",
            environment="production",
            secret_source=_FakeSecretSource({}),
            clock=FixedClock(T0),
        )
        assert context.platform_info.python_version

    def test_raises_when_required_secret_missing(self) -> None:
        with pytest.raises(RuntimeValidationError, match="API_KEY"):
            build_runtime_context(
                version="0.12.0",
                git_commit="abc1234",
                environment="production",
                required_secrets=["API_KEY"],
                secret_source=_FakeSecretSource({}),
            )

    def test_succeeds_when_required_secret_present(self) -> None:
        context = build_runtime_context(
            version="0.12.0",
            git_commit="abc1234",
            environment="production",
            required_secrets=["API_KEY"],
            secret_source=_FakeSecretSource({"API_KEY": "abc"}),
            clock=FixedClock(T0),
        )
        assert context.environment == "production"

    def test_skips_health_evaluation_when_no_checks_given(self) -> None:
        context = build_runtime_context(
            version="0.12.0",
            git_commit="abc1234",
            environment="production",
            secret_source=_FakeSecretSource({}),
            clock=FixedClock(T0),
        )
        assert context is not None

    def test_raises_when_checks_given_and_unhealthy(self) -> None:
        with pytest.raises(UnhealthyPlatformError):
            build_runtime_context(
                version="0.12.0",
                git_commit="abc1234",
                environment="production",
                secret_source=_FakeSecretSource({}),
                checks=[configuration_check(lambda: False)],
                clock=FixedClock(T0),
            )

    def test_succeeds_when_checks_given_and_healthy(self) -> None:
        context = build_runtime_context(
            version="0.12.0",
            git_commit="abc1234",
            environment="production",
            secret_source=_FakeSecretSource({}),
            checks=[configuration_check(lambda: True)],
            clock=FixedClock(T0),
        )
        assert context.environment == "production"

    def test_uses_default_env_secret_source_when_not_given(self) -> None:
        context = build_runtime_context(
            version="0.12.0",
            git_commit="abc1234",
            environment="production",
            clock=FixedClock(T0),
        )
        assert context.environment == "production"
