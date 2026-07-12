from __future__ import annotations

import numpy as np
import pytest

from hmm.exceptions import InsufficientDataError
from hmm.normalizer import ZScoreNormalizer, drop_incomplete_rows


class TestDropIncompleteRows:
    def test_keeps_rows_with_no_nan(self) -> None:
        X = np.array([[1.0, 2.0], [3.0, 4.0]])
        clean, mask = drop_incomplete_rows(X)
        assert clean.shape == (2, 2)
        assert mask.tolist() == [True, True]

    def test_drops_rows_with_any_nan(self) -> None:
        X = np.array([[1.0, 2.0], [np.nan, 4.0], [5.0, 6.0]])
        clean, mask = drop_incomplete_rows(X)
        assert clean.tolist() == [[1.0, 2.0], [5.0, 6.0]]
        assert mask.tolist() == [True, False, True]

    def test_raises_if_every_row_dropped(self) -> None:
        X = np.array([[np.nan, 1.0], [2.0, np.nan]])
        with pytest.raises(InsufficientDataError):
            drop_incomplete_rows(X)

    def test_rejects_non_2d_input(self) -> None:
        with pytest.raises(ValueError, match="2D"):
            drop_incomplete_rows(np.array([1.0, 2.0, 3.0]))


class TestZScoreNormalizer:
    def test_fit_transform_produces_zero_mean_unit_std(self) -> None:
        rng = np.random.default_rng(0)
        X = rng.normal(loc=[10.0, -5.0], scale=[2.0, 0.5], size=(500, 2))
        normalizer = ZScoreNormalizer()
        X_norm = normalizer.fit_transform(X)
        assert np.allclose(X_norm.mean(axis=0), 0.0, atol=1e-9)
        assert np.allclose(X_norm.std(axis=0), 1.0, atol=1e-9)

    def test_inverse_transform_recovers_original(self) -> None:
        rng = np.random.default_rng(1)
        X = rng.normal(size=(50, 3))
        normalizer = ZScoreNormalizer()
        X_norm = normalizer.fit_transform(X)
        assert np.allclose(normalizer.inverse_transform(X_norm), X, atol=1e-9)

    def test_constant_feature_transforms_to_zero_not_inf_or_nan(self) -> None:
        X = np.column_stack([np.full(20, 5.0), np.arange(20, dtype=float)])
        normalizer = ZScoreNormalizer()
        X_norm = normalizer.fit_transform(X)
        assert np.all(np.isfinite(X_norm))
        assert np.allclose(X_norm[:, 0], 0.0)

    def test_transform_before_fit_raises(self) -> None:
        normalizer = ZScoreNormalizer()
        with pytest.raises(InsufficientDataError, match="before fit"):
            normalizer.transform(np.zeros((1, 2)))

    def test_inverse_transform_before_fit_raises(self) -> None:
        normalizer = ZScoreNormalizer()
        with pytest.raises(InsufficientDataError, match="before fit"):
            normalizer.inverse_transform(np.zeros((1, 2)))

    def test_fit_rejects_nan(self) -> None:
        normalizer = ZScoreNormalizer()
        with pytest.raises(InsufficientDataError, match="NaN"):
            normalizer.fit(np.array([[1.0, np.nan]]))

    def test_transform_rejects_nan(self) -> None:
        normalizer = ZScoreNormalizer()
        normalizer.fit(np.array([[1.0, 2.0], [3.0, 4.0]]))
        with pytest.raises(InsufficientDataError, match="NaN"):
            normalizer.transform(np.array([[1.0, np.nan]]))

    def test_to_dict_before_fit_raises(self) -> None:
        with pytest.raises(InsufficientDataError, match="before fit"):
            ZScoreNormalizer().to_dict()

    def test_round_trips_through_dict(self) -> None:
        rng = np.random.default_rng(2)
        X = rng.normal(size=(30, 2))
        normalizer = ZScoreNormalizer()
        normalizer.fit(X)
        restored = ZScoreNormalizer.from_dict(normalizer.to_dict())
        assert np.allclose(restored.transform(X), normalizer.transform(X))
