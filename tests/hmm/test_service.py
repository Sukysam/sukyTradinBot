from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from features.feature_vector import FeatureVector
from hmm.config import HMMConfig, SelectionConfig, TrainingConfig
from hmm.exceptions import ContractViolationError, InsufficientDataError
from hmm.models import RegimeState
from hmm.service import RegimeService
from tests.hmm.conftest import make_feature_vectors, synthetic_regime_matrix

FEATURE_NAMES = ("f1", "f2")


def _history(n_per_regime: int = 100, seed: int = 42) -> list[FeatureVector]:
    rng = np.random.default_rng(seed)
    X = synthetic_regime_matrix(
        rng, regime_means=[(0.0, 0.0), (6.0, -6.0)], n_per_regime=n_per_regime
    )
    return make_feature_vectors(X, FEATURE_NAMES)


def _fast_config() -> HMMConfig:
    return HMMConfig(
        selection=SelectionConfig(candidate_states=(2, 3)),
        training=TrainingConfig(n_init=2, n_iter=100, random_state=1),
    )


class TestTrain:
    def test_returns_a_usable_service(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        assert service.symbol == "TEST"
        assert service.model_version == "v1"
        assert service.feature_names == FEATURE_NAMES
        assert service.n_states >= 1

    def test_rejects_empty_history(self) -> None:
        with pytest.raises(InsufficientDataError):
            RegimeService.train([], symbol="TEST", model_version="v1")

    def test_rejects_history_with_wrong_symbol(self) -> None:
        history = _history()
        with pytest.raises(ContractViolationError, match="symbol"):
            RegimeService.train(history, symbol="OTHER", model_version="v1", config=_fast_config())

    def test_rejects_history_with_inconsistent_feature_names(self) -> None:
        history = _history()
        bad_vector = history[0]
        bad_provenance = replace(bad_vector.provenance, feature_versions={"f1": 1, "different": 1})
        history[0] = replace(
            bad_vector,
            feature_names=("f1", "different"),
            provenance=bad_provenance,
        )
        with pytest.raises(ContractViolationError, match="feature_names"):
            RegimeService.train(history, symbol="TEST", model_version="v1", config=_fast_config())

    def test_metadata_records_training_window_from_history_timestamps(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        ordered = sorted(history, key=lambda v: v.timestamp)
        assert service.metadata.training_window_start == ordered[0].timestamp
        assert service.metadata.training_window_end == ordered[-1].timestamp

    def test_metadata_captures_feature_pipeline_version_and_feature_versions(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        assert service.metadata.feature_pipeline_version == "2"
        assert service.metadata.feature_versions == {"f1": 1, "f2": 1}

    def test_explicit_feature_names_subset_is_honored(self) -> None:
        rng = np.random.default_rng(5)
        X = synthetic_regime_matrix(
            rng, regime_means=[(0.0, 0.0, 0.0), (5.0, 5.0, 5.0)], n_per_regime=80
        )
        history = make_feature_vectors(
            X, ("a", "b", "c"), feature_versions={"a": 1, "b": 1, "c": 1}
        )
        service = RegimeService.train(
            history,
            symbol="TEST",
            model_version="v1",
            feature_names=("a", "c"),
            config=_fast_config(),
        )
        assert service.feature_names == ("a", "c")


class TestInfer:
    def test_infer_returns_the_last_regime_state(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        state = service.infer(history)
        assert isinstance(state, RegimeState)
        ordered = sorted(history, key=lambda v: v.timestamp)
        assert state.timestamp == ordered[-1].timestamp
        assert state.symbol == "TEST"
        assert state.model_version == "v1"
        assert state.feature_pipeline_version == "2"

    def test_infer_series_returns_one_state_per_vector(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        states = service.infer_series(history)
        assert len(states) == len(history)

    def test_regime_probabilities_sum_to_one_in_metadata(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        state = service.infer(history)
        probs = state.metadata["regime_probabilities"]
        assert len(probs) == service.n_states
        assert abs(sum(probs) - 1.0) < 1e-6

    def test_infer_rejects_empty_history(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        with pytest.raises(InsufficientDataError):
            service.infer([])

    def test_infer_rejects_wrong_symbol(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        other_symbol_history = [replace(v, symbol="OTHER") for v in history]
        with pytest.raises(ContractViolationError, match="symbol"):
            service.infer(other_symbol_history)

    def test_infer_rejects_missing_required_feature(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        narrowed = [
            replace(
                v,
                feature_values=(v.feature_values[0],),
                feature_names=("f1",),
                provenance=replace(v.provenance, feature_versions={"f1": 1}),
            )
            for v in history
        ]
        with pytest.raises(ContractViolationError, match="missing required feature"):
            service.infer(narrowed)

    def test_infer_rejects_nan_feature_value(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        last = history[-1]
        history[-1] = replace(last, feature_values=(float("nan"), last.feature_values[1]))
        with pytest.raises(InsufficientDataError, match="missing/NaN"):
            service.infer(history)

    def test_infer_rejects_feature_version_drift(self) -> None:
        history = _history()
        service = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        from features.feature_vector import Provenance

        last = history[-1]
        drifted_provenance = Provenance(
            pipeline_version=last.provenance.pipeline_version,
            manifest_version=last.provenance.manifest_version,
            feature_versions={"f1": 2, "f2": 1},
            generated_at=last.provenance.generated_at,
            source_dataset=last.provenance.source_dataset,
        )
        history[-1] = replace(last, provenance=drifted_provenance)
        with pytest.raises(ContractViolationError, match="different feature version"):
            service.infer(history)


class TestSaveLoad:
    def test_full_train_save_load_infer_cycle(self, tmp_path: Path) -> None:
        history = _history()
        trained = RegimeService.train(
            history, symbol="TEST", model_version="v1", config=_fast_config()
        )
        expected = trained.infer(history)

        trained.save(tmp_path)
        loaded = RegimeService.load(tmp_path, "TEST", "v1")
        actual = loaded.infer(history)

        assert actual.regime_id == expected.regime_id
        assert actual.confidence == pytest.approx(expected.confidence)
        assert actual.transition_probability == pytest.approx(expected.transition_probability)
        assert actual.model_version == expected.model_version
        assert loaded.metadata == trained.metadata
