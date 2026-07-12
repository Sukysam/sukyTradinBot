from __future__ import annotations

import numpy as np
import numpy.typing as npt

from hmm.config import SelectionConfig, SelectionCriterion, TrainingConfig
from hmm.selector import SelectionResult, aic, bic, select
from tests.hmm.conftest import synthetic_regime_matrix


def _three_regime_matrix() -> npt.NDArray[np.float64]:
    rng = np.random.default_rng(11)
    return synthetic_regime_matrix(
        rng,
        regime_means=[(0.0, 0.0), (5.0, 5.0), (-5.0, 5.0)],
        n_per_regime=80,
        std=0.8,
    )


class TestCriteria:
    def test_bic_penalizes_more_than_aic_for_same_model(self) -> None:
        # BIC's penalty term k*ln(n) exceeds AIC's 2k whenever n > e^2 (~7.4),
        # true for any realistic sample size -- so BIC(same fit) >= AIC(same fit).
        b = bic(log_likelihood=-100.0, n_samples=200, n_components=3, n_features=2)
        a = aic(log_likelihood=-100.0, n_components=3, n_features=2)
        assert b > a


class TestSelect:
    def test_selects_the_true_state_count_on_well_separated_synthetic_data(self) -> None:
        X = _three_regime_matrix()
        selection_config = SelectionConfig(candidate_states=(2, 3, 4, 5))
        training_config = TrainingConfig(n_init=3, random_state=5)
        result = select(X, selection_config, training_config)
        assert result.trained_model.n_states == 3

    def test_records_bic_and_aic_for_every_successful_candidate(self) -> None:
        X = _three_regime_matrix()
        selection_config = SelectionConfig(candidate_states=(2, 3))
        result = select(X, selection_config, TrainingConfig(n_init=2, random_state=5))
        assert set(result.bic_by_candidate) == {2, 3}
        assert set(result.aic_by_candidate) == {2, 3}

    def test_aic_criterion_used_when_configured(self) -> None:
        X = _three_regime_matrix()
        selection_config = SelectionConfig(
            candidate_states=(2, 3), criterion=SelectionCriterion.AIC
        )
        result = select(X, selection_config, TrainingConfig(n_init=2, random_state=5))
        assert result.criterion == SelectionCriterion.AIC
        best = min(result.aic_by_candidate, key=lambda k: result.aic_by_candidate[k])
        assert result.trained_model.n_states == best

    def test_bic_and_aic_properties_match_the_winning_candidate(self) -> None:
        X = _three_regime_matrix()
        result = select(
            X, SelectionConfig(candidate_states=(2, 3)), TrainingConfig(n_init=2, random_state=5)
        )
        assert result.bic == result.bic_by_candidate[result.trained_model.n_states]
        assert result.aic == result.aic_by_candidate[result.trained_model.n_states]

    def test_deterministic_given_same_seed(self) -> None:
        X = _three_regime_matrix()
        selection_config = SelectionConfig(candidate_states=(2, 3))
        training_config = TrainingConfig(n_init=2, random_state=42)
        first = select(X, selection_config, training_config)
        second = select(X, selection_config, training_config)
        assert first.trained_model.n_states == second.trained_model.n_states
        assert first.bic == second.bic

    def test_selection_result_type(self) -> None:
        X = _three_regime_matrix()
        result = select(X, SelectionConfig(candidate_states=(2,)), TrainingConfig(n_init=1))
        assert isinstance(result, SelectionResult)
