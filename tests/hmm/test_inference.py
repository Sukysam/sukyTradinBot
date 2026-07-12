from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest
from hmmlearn.hmm import GaussianHMM

from hmm.config import TrainingConfig
from hmm.inference import forward_algorithm
from hmm.trainer import train
from tests.hmm.conftest import synthetic_regime_matrix


def _fitted_model() -> tuple[GaussianHMM, npt.NDArray[np.float64]]:
    rng = np.random.default_rng(21)
    X = synthetic_regime_matrix(rng, regime_means=[(0.0, 0.0), (6.0, 6.0)], n_per_regime=100)
    return train(X, n_states=2, config=TrainingConfig(n_init=2, random_state=3)).model, X


class TestForwardAlgorithm:
    def test_returns_valid_probability_distribution_per_row(self) -> None:
        model, X = _fitted_model()
        posteriors = forward_algorithm(model, X)
        assert posteriors.shape == (X.shape[0], model.n_components)
        assert np.allclose(posteriors.sum(axis=1), 1.0)
        assert (posteriors >= 0).all()
        assert (posteriors <= 1).all()

    def test_perturbing_a_later_row_does_not_change_an_earlier_posterior(self) -> None:
        """The core causality property: P(S_t | X_{1:t}) must depend only
        on rows <= t. Perturbing the last row must not change any earlier
        row's posterior -- this is the forward-algorithm analog of
        tests/features/test_no_lookahead_all_features.py's perturbation test.
        """
        model, X = _fitted_model()
        base = forward_algorithm(model, X)

        perturbed_X = X.copy()
        perturbed_X[-1] = perturbed_X[-1] + 50.0
        perturbed = forward_algorithm(model, perturbed_X)

        assert np.allclose(base[:-1], perturbed[:-1])

    def test_single_row_input_is_the_start_distribution_times_emission(self) -> None:
        model, X = _fitted_model()
        posteriors = forward_algorithm(model, X[:1])
        assert posteriors.shape == (1, model.n_components)
        assert np.allclose(posteriors.sum(), 1.0)

    def test_rejects_non_2d_input(self) -> None:
        model, _X = _fitted_model()
        with pytest.raises(ValueError, match="2D"):
            forward_algorithm(model, np.array([1.0, 2.0]))
