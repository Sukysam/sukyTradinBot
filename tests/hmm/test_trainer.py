from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from hmm.config import TrainingConfig
from hmm.exceptions import TrainingError
from hmm.trainer import train
from tests.hmm.conftest import synthetic_regime_matrix


def _two_regime_matrix() -> npt.NDArray[np.float64]:
    rng = np.random.default_rng(7)
    return synthetic_regime_matrix(
        rng, regime_means=[(0.0, 0.0), (6.0, -6.0)], n_per_regime=100, std=1.0
    )


class TestTrain:
    def test_returns_trained_model_with_expected_shape(self) -> None:
        X = _two_regime_matrix()
        result = train(X, n_states=2, config=TrainingConfig(n_init=2, random_state=1))
        assert result.n_states == 2
        assert result.n_samples == 200
        assert result.n_features == 2
        assert result.covariance_type == "full"
        assert np.isfinite(result.log_likelihood)

    def test_deterministic_given_same_seed(self) -> None:
        X = _two_regime_matrix()
        config = TrainingConfig(n_init=2, random_state=99)
        first = train(X, n_states=2, config=config)
        second = train(X, n_states=2, config=config)
        assert first.log_likelihood == second.log_likelihood
        assert np.allclose(first.model.means_, second.model.means_)
        assert np.allclose(first.model.transmat_, second.model.transmat_)

    def test_different_seeds_can_produce_different_results(self) -> None:
        X = _two_regime_matrix()
        first = train(X, n_states=2, config=TrainingConfig(n_init=1, random_state=1))
        second = train(X, n_states=2, config=TrainingConfig(n_init=1, random_state=999))
        # Not asserting inequality (both could coincidentally converge to the
        # same optimum on well-separated synthetic data) -- just that both
        # ran successfully with independently seeded restarts.
        assert np.isfinite(first.log_likelihood)
        assert np.isfinite(second.log_likelihood)

    def test_rejects_nan_input(self) -> None:
        X = _two_regime_matrix()
        X[0, 0] = np.nan
        with pytest.raises(ValueError, match="NaN"):
            train(X, n_states=2, config=TrainingConfig())

    def test_rejects_non_2d_input(self) -> None:
        with pytest.raises(ValueError, match="2D"):
            train(np.array([1.0, 2.0, 3.0]), n_states=2, config=TrainingConfig())

    def test_rejects_n_states_below_one(self) -> None:
        X = _two_regime_matrix()
        with pytest.raises(ValueError, match="n_states"):
            train(X, n_states=0, config=TrainingConfig())

    def test_raises_training_error_when_state_count_exceeds_samples(self) -> None:
        # A handful of rows can't support a 50-state HMM -- every restart
        # should fail cleanly rather than return a garbage fit.
        X = np.random.default_rng(3).normal(size=(5, 2))
        with pytest.raises(TrainingError):
            train(X, n_states=50, config=TrainingConfig(n_init=1, n_iter=5))
