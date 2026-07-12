"""`RegimeService` -- the only class outside this package anyone should
import. Consumes only `features.feature_vector.FeatureVector` and
produces only `models.RegimeState`; never returns or accepts an
`hmmlearn.hmm.GaussianHMM`, a raw feature matrix, or a `Normalizer`
instance. See
docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt

from common.interfaces import Clock
from common.time import SystemClock
from features.feature_vector import FeatureVector
from hmm import persistence, selector
from hmm.config import HMMConfig
from hmm.exceptions import ContractViolationError, InsufficientDataError
from hmm.inference import forward_algorithm
from hmm.models import ModelMetadata, RegimeState, TrainedModel
from hmm.normalizer import ZScoreNormalizer, drop_incomplete_rows


def _extract_matrix(
    history: Sequence[FeatureVector], feature_names: Sequence[str]
) -> npt.NDArray[np.float64]:
    rows = []
    for vec in history:
        try:
            rows.append([vec.get(name) for name in feature_names])
        except KeyError as exc:
            raise ContractViolationError(
                f"FeatureVector for {vec.symbol!r} at {vec.timestamp.isoformat()} is "
                f"missing a required feature: {exc}"
            ) from exc
    return np.asarray(rows, dtype=np.float64)


class RegimeService:
    """Wraps exactly one trained/loaded model. Construct via `train()` or
    `load()`, never directly -- both classmethods return a fully-formed
    instance so there is no intermediate state where `infer()` could be
    called before a model actually exists.
    """

    def __init__(
        self,
        trained_model: TrainedModel,
        normalizer: ZScoreNormalizer,
        metadata: ModelMetadata,
        clock: Clock | None = None,
    ) -> None:
        self._trained_model = trained_model
        self._normalizer = normalizer
        self._metadata = metadata
        self._clock = clock or SystemClock()

    @property
    def model_version(self) -> str:
        return self._metadata.model_version

    @property
    def symbol(self) -> str:
        return self._metadata.symbol

    @property
    def n_states(self) -> int:
        return self._trained_model.n_states

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self._metadata.feature_names

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    @classmethod
    def train(
        cls,
        history: Sequence[FeatureVector],
        *,
        symbol: str,
        model_version: str,
        feature_names: Sequence[str] | None = None,
        config: HMMConfig | None = None,
        clock: Clock | None = None,
    ) -> RegimeService:
        """Fit a fresh model against `history` (ascending or not -- sorted
        defensively). `feature_names` defaults to `history[0].feature_names`
        if not given; every vector in `history` must carry at least that
        set (a superset, e.g. every vector's full registry output, is
        fine -- only the requested names are extracted, via `.get(name)`,
        never positional indexing, per Standards/FeatureVector Contract.md's
        ordering guarantees). Rows with any missing/NaN required feature
        are dropped (see `normalizer.drop_incomplete_rows`) before
        normalization and fitting -- never silently imputed.
        """
        if not history:
            raise InsufficientDataError("cannot train on an empty history")
        config = config or HMMConfig()
        clock = clock or SystemClock()

        ordered = sorted(history, key=lambda v: v.timestamp)
        symbols = {v.symbol for v in ordered}
        if symbols != {symbol}:
            raise ContractViolationError(
                f"history symbol(s) {sorted(symbols)} do not match requested symbol {symbol!r}"
            )

        resolved_feature_names = (
            tuple(feature_names) if feature_names is not None else ordered[0].feature_names
        )
        for vec in ordered:
            missing_names = set(resolved_feature_names) - set(vec.feature_names)
            if missing_names:
                raise ContractViolationError(
                    f"FeatureVector for {vec.symbol!r} at {vec.timestamp.isoformat()} is "
                    f"missing required feature_names {sorted(missing_names)}"
                )

        X = _extract_matrix(ordered, resolved_feature_names)
        X_clean, _ = drop_incomplete_rows(X)

        normalizer = ZScoreNormalizer()
        X_norm = normalizer.fit_transform(X_clean)

        selection_result = selector.select(X_norm, config.selection, config.training)
        trained_model = selection_result.trained_model

        latest_vector = ordered[-1]
        feature_versions = {
            name: latest_vector.provenance.feature_versions[name] for name in resolved_feature_names
        }
        metadata = ModelMetadata(
            model_version=model_version,
            symbol=symbol,
            feature_pipeline_version=latest_vector.provenance.pipeline_version,
            feature_names=resolved_feature_names,
            feature_versions=feature_versions,
            training_window_start=ordered[0].timestamp,
            training_window_end=ordered[-1].timestamp,
            n_states=trained_model.n_states,
            covariance_type=trained_model.covariance_type,
            random_state=trained_model.random_state,
            selection_criterion=selection_result.criterion.value,
            bic=selection_result.bic,
            aic=selection_result.aic,
            log_likelihood=trained_model.log_likelihood,
            n_samples=trained_model.n_samples,
            converged=trained_model.converged,
            n_iter_used=trained_model.n_iter_used,
            trained_at=clock.now(),
        )
        return cls(trained_model, normalizer, metadata, clock=clock)

    @classmethod
    def load(
        cls, base_dir: Path, symbol: str, model_version: str, clock: Clock | None = None
    ) -> RegimeService:
        trained_model, normalizer, metadata = persistence.load(base_dir, symbol, model_version)
        return cls(trained_model, normalizer, metadata, clock=clock)

    def save(self, base_dir: Path) -> Path:
        return persistence.save(base_dir, self._trained_model, self._normalizer, self._metadata)

    def _validate_contract(self, history: Sequence[FeatureVector]) -> None:
        symbols = {v.symbol for v in history}
        if symbols != {self._metadata.symbol}:
            raise ContractViolationError(
                f"history symbol(s) {sorted(symbols)} do not match this model's "
                f"symbol {self._metadata.symbol!r}"
            )
        expected_names = set(self._metadata.feature_names)
        for vec in history:
            missing_names = expected_names - set(vec.feature_names)
            if missing_names:
                raise ContractViolationError(
                    f"FeatureVector for {vec.symbol!r} at {vec.timestamp.isoformat()} is "
                    f"missing required feature(s): {sorted(missing_names)}"
                )
            drifted = {
                name: (self._metadata.feature_versions[name], vec.provenance.feature_versions[name])
                for name in self._metadata.feature_names
                if vec.provenance.feature_versions[name] != self._metadata.feature_versions[name]
            }
            if drifted:
                raise ContractViolationError(
                    f"FeatureVector for {vec.symbol!r} at {vec.timestamp.isoformat()} was "
                    f"computed with different feature version(s) than this model was trained "
                    f"on -- {drifted} (format: {{name: (trained_version, vector_version)}}). "
                    "Retrain against the current feature definitions before using this model."
                )

    def infer_series(self, history: Sequence[FeatureVector]) -> list[RegimeState]:
        """One `RegimeState` per input vector, using only that vector and
        everything before it in `history` -- the causal Forward Algorithm
        run over the whole window each call (see `inference.
        forward_algorithm`'s docstring on why this isn't a persistent,
        incremental filter).
        """
        if not history:
            raise InsufficientDataError("cannot infer on an empty history")
        ordered = sorted(history, key=lambda v: v.timestamp)
        self._validate_contract(ordered)

        X = _extract_matrix(ordered, self._metadata.feature_names)
        if np.isnan(X).any():
            raise InsufficientDataError(
                "history contains a missing/NaN value for a required feature -- regime "
                "inference needs every required feature present for every row, unlike a "
                "single rolling indicator's warmup NaN"
            )
        X_norm = self._normalizer.transform(X)
        posteriors = forward_algorithm(self._trained_model.model, X_norm)
        transmat = self._trained_model.model.transmat_

        states = []
        for i, vec in enumerate(ordered):
            regime_id = int(np.argmax(posteriors[i]))
            states.append(
                RegimeState(
                    timestamp=vec.timestamp,
                    symbol=vec.symbol,
                    regime_id=regime_id,
                    confidence=float(posteriors[i, regime_id]),
                    transition_probability=float(transmat[regime_id, regime_id]),
                    model_version=self._metadata.model_version,
                    feature_pipeline_version=vec.provenance.pipeline_version,
                    metadata={
                        "regime_probabilities": tuple(float(p) for p in posteriors[i]),
                        "n_states": self._trained_model.n_states,
                    },
                )
            )
        return states

    def infer(self, history: Sequence[FeatureVector]) -> RegimeState:
        """The single most recent `RegimeState` -- the live-trading entry
        point, mirroring `FeaturePipeline.compute()`'s "recompute over the
        given window, return the last one" shape.
        """
        return self.infer_series(history)[-1]


__all__ = ["RegimeService"]
