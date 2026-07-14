"""Tests for `memory.config.MemoryConfig`'s construction-time validation."""

from __future__ import annotations

import pytest

from memory.config import MemoryConfig


class TestMemoryConfig:
    def test_defaults_are_valid(self) -> None:
        config = MemoryConfig()
        assert config.prior_alpha == 1.0
        assert config.prior_beta == 1.0

    def test_rejects_nonpositive_prior_alpha(self) -> None:
        with pytest.raises(ValueError, match="prior_alpha"):
            MemoryConfig(prior_alpha=0.0)

    def test_rejects_nonpositive_prior_beta(self) -> None:
        with pytest.raises(ValueError, match="prior_beta"):
            MemoryConfig(prior_beta=-1.0)

    def test_rejects_nonpositive_confidence_smoothing(self) -> None:
        with pytest.raises(ValueError, match="confidence_smoothing"):
            MemoryConfig(confidence_smoothing=0.0)

    def test_rejects_empty_model_version(self) -> None:
        with pytest.raises(ValueError, match="model_version"):
            MemoryConfig(model_version="")

    def test_is_frozen(self) -> None:
        config = MemoryConfig()
        with pytest.raises(AttributeError):
            config.prior_alpha = 2.0  # type: ignore[misc]
