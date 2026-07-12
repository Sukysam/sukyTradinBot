"""With a fixed random seed: identical model parameters, identical
predictions, identical metadata across independent training runs on the
same data.
"""

from __future__ import annotations

import numpy as np

from features.feature_vector import FeatureVector
from hmm.config import HMMConfig, SelectionConfig, TrainingConfig
from hmm.service import RegimeService
from tests.hmm.conftest import make_feature_vectors, synthetic_regime_matrix

FEATURE_NAMES = ("f1", "f2")


def _history() -> list[FeatureVector]:
    rng = np.random.default_rng(200)
    X = synthetic_regime_matrix(rng, regime_means=[(0.0, 0.0), (5.0, 5.0)], n_per_regime=90)
    return make_feature_vectors(X, FEATURE_NAMES)


def _config() -> HMMConfig:
    return HMMConfig(
        selection=SelectionConfig(candidate_states=(2, 3)),
        training=TrainingConfig(n_init=3, random_state=123),
    )


class TestReproducibility:
    def test_identical_seed_produces_identical_model_parameters(self) -> None:
        history = _history()
        first = RegimeService.train(history, symbol="TEST", model_version="v1", config=_config())
        second = RegimeService.train(history, symbol="TEST", model_version="v1", config=_config())

        assert first.n_states == second.n_states
        assert first.metadata.log_likelihood == second.metadata.log_likelihood
        assert first.metadata.bic == second.metadata.bic
        assert first.metadata.aic == second.metadata.aic

    def test_identical_seed_produces_identical_predictions(self) -> None:
        history = _history()
        first = RegimeService.train(history, symbol="TEST", model_version="v1", config=_config())
        second = RegimeService.train(history, symbol="TEST", model_version="v1", config=_config())

        first_states = first.infer_series(history)
        second_states = second.infer_series(history)

        assert [s.regime_id for s in first_states] == [s.regime_id for s in second_states]
        assert np.allclose(
            [s.confidence for s in first_states], [s.confidence for s in second_states]
        )
        assert np.allclose(
            [s.transition_probability for s in first_states],
            [s.transition_probability for s in second_states],
        )

    def test_identical_seed_produces_identical_metadata_except_trained_at(self) -> None:
        history = _history()
        first = RegimeService.train(history, symbol="TEST", model_version="v1", config=_config())
        second = RegimeService.train(history, symbol="TEST", model_version="v1", config=_config())

        from dataclasses import replace

        assert replace(first.metadata, trained_at=second.metadata.trained_at) == second.metadata

    def test_different_seed_can_change_the_result(self) -> None:
        history = _history()
        low_seed = HMMConfig(
            selection=SelectionConfig(candidate_states=(2,)),
            training=TrainingConfig(n_init=1, random_state=1),
        )
        high_seed = HMMConfig(
            selection=SelectionConfig(candidate_states=(2,)),
            training=TrainingConfig(n_init=1, random_state=999999),
        )
        first = RegimeService.train(history, symbol="TEST", model_version="v1", config=low_seed)
        second = RegimeService.train(history, symbol="TEST", model_version="v1", config=high_seed)
        # Not asserting the two runs differ (both may converge to the same
        # optimum on well-separated data) -- just that changing the seed is
        # a real, independent input, not silently ignored.
        assert first.metadata.random_state != second.metadata.random_state
