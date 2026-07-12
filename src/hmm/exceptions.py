"""Exception hierarchy for the HMM & Regime Detection package.

All derive from `HMMError` (itself an `AppError`, per
docs/engineering-handbook/Standards/Coding Standards.md's "catch specific
exceptions, fail loudly, never swallow silently") so a caller can catch
"something in regime detection went wrong" without also swallowing
unrelated errors.
"""

from __future__ import annotations

from common.errors import AppError


class HMMError(AppError):
    """Base class for all errors raised by `hmm`."""


class InsufficientDataError(HMMError):
    """Raised when there isn't enough clean (non-NaN) data to train,
    select, or run inference -- e.g. every row in a training window has
    at least one missing feature, or a single `FeatureVector` handed to
    `infer` has a NaN/flagged value for a feature the model needs.
    """


class TrainingError(HMMError):
    """Raised when Baum-Welch/EM fitting fails for every candidate state
    count / random restart -- never silently falls back to an
    unconverged or partially-fit model.
    """


class ModelNotFittedError(HMMError):
    """Raised when inference or persistence is attempted against a
    `RegimeService` that has neither been trained nor loaded yet.
    """


class PersistenceError(HMMError):
    """Raised when a model artifact (`model.pkl`, `normalizer.pkl`,
    `metadata.json`) is missing, corrupt, or internally inconsistent on
    load -- never silently returns a partially-loaded model.
    """


class ContractViolationError(HMMError):
    """Raised when a `FeatureVector` handed to `infer`/`infer_series`
    doesn't satisfy what the loaded model actually needs -- missing a
    required feature name, or (see
    docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md) a
    `provenance.feature_versions` mismatch against what the model was
    trained on, which would otherwise silently feed drifted feature
    semantics into a live regime call.
    """


__all__ = [
    "ContractViolationError",
    "HMMError",
    "InsufficientDataError",
    "ModelNotFittedError",
    "PersistenceError",
    "TrainingError",
]
