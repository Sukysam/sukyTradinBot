"""Tests for `orchestration.config.OrchestrationConfig`'s construction-time
validation."""

from __future__ import annotations

import pytest

from orchestration.config import OrchestrationConfig


class TestOrchestrationConfig:
    def test_defaults_are_valid(self) -> None:
        config = OrchestrationConfig()
        assert config.agreement_tolerance == 0.05
        assert config.disagreement_penalty == 0.5

    def test_rejects_negative_agreement_tolerance(self) -> None:
        with pytest.raises(ValueError, match="agreement_tolerance"):
            OrchestrationConfig(agreement_tolerance=-0.01)

    def test_rejects_zero_disagreement_penalty(self) -> None:
        with pytest.raises(ValueError, match="disagreement_penalty"):
            OrchestrationConfig(disagreement_penalty=0.0)

    def test_rejects_disagreement_penalty_above_one(self) -> None:
        with pytest.raises(ValueError, match="disagreement_penalty"):
            OrchestrationConfig(disagreement_penalty=1.1)

    def test_allows_disagreement_penalty_equal_to_one(self) -> None:
        config = OrchestrationConfig(disagreement_penalty=1.0)
        assert config.disagreement_penalty == 1.0

    def test_is_frozen(self) -> None:
        config = OrchestrationConfig()
        with pytest.raises(AttributeError):
            config.agreement_tolerance = 0.1  # type: ignore[misc]
