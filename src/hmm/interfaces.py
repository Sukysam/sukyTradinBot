"""`Protocol`s for the pluggable pieces of this package -- continuing the
pattern established in `market_data.interfaces`/`common.interfaces`
(define the interface before implementing against it, so a second
implementation is a real, low-cost possibility rather than a rewrite).
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy.typing as npt


class Normalizer(Protocol):
    """Fits a deterministic transform on training data and applies it to
    both training and inference data. `trainer.py` never sees a raw
    feature matrix -- only a `Normalizer`'s `transform` output. The only
    implementation today is `normalizer.ZScoreNormalizer`; this exists so
    a future normalization strategy is a new class satisfying this
    `Protocol`, not a change to every module that currently imports
    `ZScoreNormalizer` directly.
    """

    def fit(self, X: npt.NDArray[Any]) -> None:
        """Fit on `X` (n_samples, n_features), no NaN values. Idempotent
        per instance -- call once per trained model, not per inference.
        """
        ...

    def transform(self, X: npt.NDArray[Any]) -> npt.NDArray[Any]:
        """Apply the fitted transform. Raises if called before `fit`, and
        raises (never silently produces NaN/inf) if `X` contains NaN.
        """
        ...

    def inverse_transform(self, X: npt.NDArray[Any]) -> npt.NDArray[Any]:
        """Undo `transform` -- primarily for inspecting/debugging fitted
        model parameters (e.g. HMM component means) in original feature
        units, not part of the training/inference hot path.
        """
        ...

    def to_dict(self) -> dict[str, Any]:
        """This normalizer's fitted state as a JSON-serializable dict --
        `persistence.py`'s `normalizer.pkl` is a pickle of this dict, not
        of the `Normalizer` instance itself, so the persisted format
        doesn't depend on this class's Python implementation surviving
        unchanged across versions.
        """
        ...


__all__ = ["Normalizer"]
