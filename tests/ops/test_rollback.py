"""Tests for `ops.rollback`: `select_rollback_target` and
`require_rollback_target`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ops.exceptions import NoRollbackTargetError
from ops.models import DeploymentInfo
from ops.rollback import require_rollback_target, select_rollback_target

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _deployment(deployment_id: str) -> DeploymentInfo:
    return DeploymentInfo(
        version="0.12.0",
        git_commit="abc1234",
        build_time=T0,
        deployment_environment="production",
        deployment_id=deployment_id,
    )


class TestSelectRollbackTarget:
    def test_returns_none_for_empty_history(self) -> None:
        current = _deployment("deploy-001")
        assert select_rollback_target((), current=current) is None

    def test_returns_none_when_history_only_contains_current(self) -> None:
        current = _deployment("deploy-001")
        assert select_rollback_target((current,), current=current) is None

    def test_returns_most_recent_prior_deployment(self) -> None:
        first = _deployment("deploy-001")
        second = _deployment("deploy-002")
        current = _deployment("deploy-003")
        target = select_rollback_target((first, second, current), current=current)
        assert target is second

    def test_skips_current_if_it_appears_earlier_in_history(self) -> None:
        first = _deployment("deploy-001")
        current = _deployment("deploy-002")
        target = select_rollback_target((first, current), current=current)
        assert target is first


class TestRequireRollbackTarget:
    def test_returns_target_when_present(self) -> None:
        target = _deployment("deploy-001")
        assert require_rollback_target(target) is target

    def test_raises_when_none(self) -> None:
        with pytest.raises(NoRollbackTargetError):
            require_rollback_target(None)
