from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from hmm import persistence
from hmm.config import TrainingConfig
from hmm.exceptions import PersistenceError
from hmm.models import ModelMetadata, TrainedModel
from hmm.normalizer import ZScoreNormalizer
from hmm.trainer import train
from tests.hmm.conftest import synthetic_regime_matrix

UTC = timezone.utc


def _artifact(tmp_path: Path) -> tuple[TrainedModel, ZScoreNormalizer, ModelMetadata]:
    rng = np.random.default_rng(31)
    X = synthetic_regime_matrix(rng, regime_means=[(0.0, 0.0), (5.0, 5.0)], n_per_regime=60)
    normalizer = ZScoreNormalizer()
    X_norm = normalizer.fit_transform(X)
    trained_model = train(X_norm, n_states=2, config=TrainingConfig(n_init=2, random_state=1))
    metadata = ModelMetadata(
        model_version="v1",
        symbol="TEST",
        feature_pipeline_version="2",
        feature_names=("f1", "f2"),
        feature_versions={"f1": 1, "f2": 1},
        training_window_start=datetime(2024, 1, 1, tzinfo=UTC),
        training_window_end=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=119),
        n_states=trained_model.n_states,
        covariance_type=trained_model.covariance_type,
        random_state=trained_model.random_state,
        selection_criterion="bic",
        bic=123.0,
        aic=110.0,
        log_likelihood=trained_model.log_likelihood,
        n_samples=trained_model.n_samples,
        converged=trained_model.converged,
        n_iter_used=trained_model.n_iter_used,
        trained_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    return trained_model, normalizer, metadata


class TestSaveLoad:
    def test_round_trip_preserves_model_predictions(self, tmp_path: Path) -> None:
        trained_model, normalizer, metadata = _artifact(tmp_path)
        persistence.save(tmp_path, trained_model, normalizer, metadata)
        loaded_model, loaded_normalizer, loaded_metadata = persistence.load(
            tmp_path, metadata.symbol, metadata.model_version
        )

        assert loaded_metadata == metadata
        assert np.allclose(loaded_model.model.means_, trained_model.model.means_)
        assert np.allclose(loaded_model.model.transmat_, trained_model.model.transmat_)
        assert loaded_normalizer.mean_ is not None and normalizer.mean_ is not None
        assert loaded_normalizer.std_ is not None and normalizer.std_ is not None
        assert np.allclose(loaded_normalizer.mean_, normalizer.mean_)
        assert np.allclose(loaded_normalizer.std_, normalizer.std_)

    def test_creates_versioned_symbol_scoped_directory(self, tmp_path: Path) -> None:
        trained_model, normalizer, metadata = _artifact(tmp_path)
        target = persistence.save(tmp_path, trained_model, normalizer, metadata)
        assert target == tmp_path / metadata.symbol / metadata.model_version
        assert (target / "model.pkl").exists()
        assert (target / "normalizer.pkl").exists()
        assert (target / "metadata.json").exists()

    def test_retraining_a_second_version_does_not_overwrite_the_first(self, tmp_path: Path) -> None:
        trained_model, normalizer, metadata = _artifact(tmp_path)
        persistence.save(tmp_path, trained_model, normalizer, metadata)

        from dataclasses import replace

        v2_metadata = replace(metadata, model_version="v2")
        persistence.save(tmp_path, trained_model, normalizer, v2_metadata)

        assert (tmp_path / metadata.symbol / "v1" / "metadata.json").exists()
        assert (tmp_path / metadata.symbol / "v2" / "metadata.json").exists()

    def test_rejects_mismatched_n_states(self, tmp_path: Path) -> None:
        trained_model, normalizer, metadata = _artifact(tmp_path)
        from dataclasses import replace

        bad_metadata = replace(metadata, n_states=metadata.n_states + 1)
        with pytest.raises(PersistenceError, match="n_states"):
            persistence.save(tmp_path, trained_model, normalizer, bad_metadata)


class TestLoadErrors:
    def test_missing_artifact_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PersistenceError, match="missing artifact"):
            persistence.load(tmp_path, "NOPE", "v1")

    def test_corrupt_metadata_raises(self, tmp_path: Path) -> None:
        trained_model, normalizer, metadata = _artifact(tmp_path)
        target = persistence.save(tmp_path, trained_model, normalizer, metadata)
        (target / "metadata.json").write_text("{}")
        with pytest.raises(PersistenceError, match="corrupt metadata"):
            persistence.load(tmp_path, metadata.symbol, metadata.model_version)

    def test_corrupt_model_pickle_raises(self, tmp_path: Path) -> None:
        trained_model, normalizer, metadata = _artifact(tmp_path)
        target = persistence.save(tmp_path, trained_model, normalizer, metadata)
        (target / "model.pkl").write_bytes(b"not a pickle")
        with pytest.raises(PersistenceError, match="corrupt model"):
            persistence.load(tmp_path, metadata.symbol, metadata.model_version)
