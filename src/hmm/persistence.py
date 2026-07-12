"""Save/load a trained model artifact: `model.pkl` (the fitted
`GaussianHMM`), `normalizer.pkl` (the fitted normalizer's `to_dict()`
output, pickled -- not the class instance itself, so the persisted format
doesn't depend on `ZScoreNormalizer`'s Python implementation surviving
unchanged), and `metadata.json` (via `common.io.atomic_write_json`, the
one durable-write primitive every state file in this repository already
uses).

Layout: `{base_dir}/{symbol}/{model_version}/{model.pkl, normalizer.pkl,
metadata.json}` -- scoped per symbol because a regime model is expected to
be fit per ticker (see `regime-trader/main.py`'s `ModelStore.get_model
(ticker)` Protocol and Known Gaps item 3), and per version so retraining
never silently overwrites a prior, possibly-still-in-use artifact.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

from common.io import atomic_write_json
from hmm.exceptions import PersistenceError
from hmm.models import ModelMetadata, TrainedModel
from hmm.normalizer import ZScoreNormalizer

_MODEL_FILENAME = "model.pkl"
_NORMALIZER_FILENAME = "normalizer.pkl"
_METADATA_FILENAME = "metadata.json"


def artifact_dir(base_dir: Path, symbol: str, model_version: str) -> Path:
    return base_dir / symbol / model_version


def save(
    base_dir: Path,
    trained_model: TrainedModel,
    normalizer: ZScoreNormalizer,
    metadata: ModelMetadata,
) -> Path:
    """Write the three artifact files, return the directory they landed
    in. `trained_model`/`metadata` must agree on `n_states` -- checked
    here so a mismatched pair can never be written silently.
    """
    if trained_model.n_states != metadata.n_states:
        raise PersistenceError(
            f"trained_model.n_states ({trained_model.n_states}) != "
            f"metadata.n_states ({metadata.n_states})"
        )
    target_dir = artifact_dir(base_dir, metadata.symbol, metadata.model_version)
    target_dir.mkdir(parents=True, exist_ok=True)

    with (target_dir / _MODEL_FILENAME).open("wb") as f:
        pickle.dump(trained_model.model, f)
    with (target_dir / _NORMALIZER_FILENAME).open("wb") as f:
        pickle.dump(normalizer.to_dict(), f)
    atomic_write_json(target_dir / _METADATA_FILENAME, metadata.to_dict())

    return target_dir


def load(
    base_dir: Path, symbol: str, model_version: str
) -> tuple[TrainedModel, ZScoreNormalizer, ModelMetadata]:
    """Read all three artifact files back. Raises `PersistenceError` if
    any file is missing or fails to deserialize -- never returns a
    partially-loaded model.
    """
    target_dir = artifact_dir(base_dir, symbol, model_version)
    model_path = target_dir / _MODEL_FILENAME
    normalizer_path = target_dir / _NORMALIZER_FILENAME
    metadata_path = target_dir / _METADATA_FILENAME

    for path in (model_path, normalizer_path, metadata_path):
        if not path.exists():
            raise PersistenceError(f"missing artifact file: {path}")

    try:
        with metadata_path.open("r", encoding="utf-8") as f:
            metadata = ModelMetadata.from_dict(json.load(f))
    except (KeyError, ValueError) as exc:
        raise PersistenceError(f"corrupt metadata.json at {metadata_path}: {exc}") from exc

    try:
        with model_path.open("rb") as f:
            model = pickle.load(f)
    except (pickle.UnpicklingError, EOFError, AttributeError) as exc:
        raise PersistenceError(f"corrupt model.pkl at {model_path}: {exc}") from exc

    try:
        with normalizer_path.open("rb") as f:
            normalizer_dict = pickle.load(f)
        normalizer = ZScoreNormalizer.from_dict(normalizer_dict)
    except (pickle.UnpicklingError, EOFError, KeyError) as exc:
        raise PersistenceError(f"corrupt normalizer.pkl at {normalizer_path}: {exc}") from exc

    trained_model = TrainedModel(
        model=model,
        n_states=metadata.n_states,
        covariance_type=metadata.covariance_type,
        random_state=metadata.random_state,
        log_likelihood=metadata.log_likelihood,
        converged=metadata.converged,
        n_iter_used=metadata.n_iter_used,
        n_samples=metadata.n_samples,
        n_features=len(metadata.feature_names),
    )
    return trained_model, normalizer, metadata


__all__ = ["artifact_dir", "load", "save"]
