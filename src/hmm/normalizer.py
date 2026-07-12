"""Deterministic feature normalization -- the boundary between raw
`FeatureVector` values and everything `trainer.py`/`selector.py`/
`inference.py` do. Per Milestone 4's mandate, the trainer never sees a raw
feature matrix; every value it touches has already passed through a fitted
`ZScoreNormalizer`.

Missing-value handling is deliberately explicit, not automatic: NaN rows
are never silently imputed (mean-filled, forward-filled, or otherwise) --
see `drop_incomplete_rows` below and
docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md's
rationale. A rolling technical indicator can legitimately flag-and-NaN a
single value during warmup; a regime call cannot be "70% computed" the
same way, so this package fails loudly on missing data rather than
guessing a value for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from hmm.exceptions import InsufficientDataError

_ZERO_STD_FLOOR = 1e-12


def drop_incomplete_rows(
    X: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    """Return `(X_clean, kept_mask)`: `X` with every row containing at
    least one NaN removed, and a boolean mask (same length as the input)
    marking which rows were kept -- so a caller can re-align the dropped
    rows against the `FeatureVector`s (or timestamps) they came from.
    Raises `InsufficientDataError` if every row is dropped.
    """
    if X.ndim != 2:
        raise ValueError(f"X must be 2D (n_samples, n_features), got shape {X.shape}")
    kept_mask = ~np.isnan(X).any(axis=1)
    if not kept_mask.any():
        raise InsufficientDataError(
            f"every one of {X.shape[0]} row(s) has at least one NaN feature; "
            "nothing left to train on"
        )
    return X[kept_mask], kept_mask


@dataclass
class ZScoreNormalizer:
    """`(x - mean) / std` per feature, fitted once on training data.

    `std` values at or below `_ZERO_STD_FLOOR` (a constant feature --
    see `tests/hmm/test_normalizer.py`'s constant-series case) are
    floored to `_ZERO_STD_FLOOR` before dividing, so a zero-variance
    feature transforms to `0.0` (not `inf`/`nan`) rather than crashing or
    silently propagating a non-finite value into the HMM.
    """

    mean_: npt.NDArray[np.float64] | None = field(default=None, repr=False)
    std_: npt.NDArray[np.float64] | None = field(default=None, repr=False)

    def fit(self, X: npt.NDArray[np.float64]) -> None:
        if X.ndim != 2:
            raise ValueError(f"X must be 2D (n_samples, n_features), got shape {X.shape}")
        if np.isnan(X).any():
            raise InsufficientDataError(
                "fit() received NaN values -- call drop_incomplete_rows() first"
            )
        self.mean_ = X.mean(axis=0)
        self.std_ = np.clip(X.std(axis=0), _ZERO_STD_FLOOR, None)

    def transform(self, X: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        if self.mean_ is None or self.std_ is None:
            raise InsufficientDataError("transform() called before fit()")
        if np.isnan(X).any():
            raise InsufficientDataError("transform() received NaN values")
        return (X - self.mean_) / self.std_

    def fit_transform(self, X: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        self.fit(X)
        return self.transform(X)

    def inverse_transform(self, X: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        if self.mean_ is None or self.std_ is None:
            raise InsufficientDataError("inverse_transform() called before fit()")
        return X * self.std_ + self.mean_

    def to_dict(self) -> dict[str, Any]:
        if self.mean_ is None or self.std_ is None:
            raise InsufficientDataError("to_dict() called before fit()")
        return {"mean": self.mean_.tolist(), "std": self.std_.tolist()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ZScoreNormalizer:
        return cls(
            mean_=np.asarray(data["mean"], dtype=np.float64),
            std_=np.asarray(data["std"], dtype=np.float64),
        )


__all__ = ["ZScoreNormalizer", "drop_incomplete_rows"]
