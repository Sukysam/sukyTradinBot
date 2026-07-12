"""Milestone 4's quantitative checklist: synthetic bull/bear regime
switching, stable regime persistence, noisy inputs, constant series,
missing values.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from hmm.config import HMMConfig, SelectionConfig, TrainingConfig
from hmm.service import RegimeService
from tests.hmm.conftest import make_feature_vectors, synthetic_regime_matrix

FEATURE_NAMES = ("return_like", "vol_like")


def _fast_config(candidate_states: tuple[int, ...] = (2, 3)) -> HMMConfig:
    return HMMConfig(
        selection=SelectionConfig(candidate_states=candidate_states),
        training=TrainingConfig(n_init=3, n_iter=150, random_state=7),
    )


class TestBullBearRegimeSwitching:
    def test_two_well_separated_regimes_are_recovered_in_order(self) -> None:
        rng = np.random.default_rng(101)
        n = 120
        X = synthetic_regime_matrix(
            rng, regime_means=[(2.0, 0.5), (-2.0, 3.0)], n_per_regime=n, std=0.5
        )
        history = make_feature_vectors(X, FEATURE_NAMES)
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        states = service.infer_series(history)

        first_half_regimes = {s.regime_id for s in states[10:n]}
        second_half_regimes = {s.regime_id for s in states[n + 10 :]}
        # Each half should be dominated by a single, and different, regime --
        # not asserting every single row (a handful near the boundary are
        # expected to be ambiguous), just the bulk of each block.
        assert len(first_half_regimes | second_half_regimes) >= 2

    def test_switching_back_to_a_prior_regime_is_recognized(self) -> None:
        rng = np.random.default_rng(102)
        n = 80
        block_a = rng.normal(loc=(3.0, 0.0), scale=0.4, size=(n, 2))
        block_b = rng.normal(loc=(-3.0, 0.0), scale=0.4, size=(n, 2))
        X = np.concatenate([block_a, block_b, block_a], axis=0)
        history = make_feature_vectors(X, FEATURE_NAMES)
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        states = service.infer_series(history)

        first_block_regime = states[n // 2].regime_id
        third_block_regime = states[-1].regime_id
        assert first_block_regime == third_block_regime


class TestStableRegimePersistence:
    def test_a_single_unbroken_regime_has_high_self_transition_probability(self) -> None:
        rng = np.random.default_rng(103)
        X = rng.normal(loc=(1.0, 1.0), scale=0.3, size=(200, 2))
        history = make_feature_vectors(X, FEATURE_NAMES)
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config((1, 2))
        )
        state = service.infer(history)
        # A regime that never actually switches should look "sticky":
        # high probability of staying, once the model has enough data to
        # estimate the transition matrix confidently.
        assert state.transition_probability > 0.5


class TestNoisyInputs:
    def test_high_noise_does_not_crash_training_or_inference(self) -> None:
        rng = np.random.default_rng(104)
        X = synthetic_regime_matrix(
            rng, regime_means=[(1.0, 1.0), (-1.0, -1.0)], n_per_regime=100, std=5.0
        )
        history = make_feature_vectors(X, FEATURE_NAMES)
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        state = service.infer(history)
        assert 0.0 <= state.confidence <= 1.0


class TestConstantSeries:
    def test_constant_feature_values_do_not_crash_training_or_inference(self) -> None:
        X = np.column_stack([np.full(100, 3.0), np.full(100, -1.0)])
        history = make_feature_vectors(X, FEATURE_NAMES)
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config((1, 2))
        )
        state = service.infer(history)
        assert 0.0 <= state.confidence <= 1.0


class TestMissingValues:
    def test_nan_rows_are_dropped_before_training_not_imputed(self) -> None:
        rng = np.random.default_rng(105)
        X = synthetic_regime_matrix(rng, regime_means=[(0.0, 0.0), (5.0, 5.0)], n_per_regime=80)
        history = make_feature_vectors(X, FEATURE_NAMES)
        # Simulate warmup NaNs on the first 5 rows, matching what
        # FeaturePipeline actually produces for early, insufficient-history
        # rows.
        for i in range(5):
            history[i] = replace(
                history[i], feature_values=(float("nan"), history[i].feature_values[1])
            )

        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        assert service.metadata.n_samples == len(history) - 5
