"""`RegimeState` -- the single contract `RegimeService.infer`/`infer_series`
return, and the only thing about this package any downstream consumer
(Strategy Engine, backtesting, risk) is meant to depend on. Frozen per
docs/engineering-handbook/Architecture/ADR/ADR-006-RegimeState-Contract.md;
full detail in
"docs/engineering-handbook/Standards/RegimeState Contract.md".

Also holds this package's *internal* dataclasses (`TrainedModel`,
`ModelMetadata`) -- never returned from `RegimeService`'s public methods,
never crossing the package boundary. `TrainedModel.model` is the one place
an `hmmlearn.hmm.GaussianHMM` object exists anywhere in this codebase
outside `trainer.py`/`selector.py`/`inference.py`/`persistence.py`
themselves; see those modules' docstrings and ADR-007 for why nothing
outside this package ever sees it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from common.time import require_utc

if TYPE_CHECKING:
    from hmmlearn.hmm import GaussianHMM


@dataclass(frozen=True)
class RegimeState:
    """One symbol's regime call as of one point in time.

    `regime_id` is the filtered MAP state estimate (argmax of `P(S_t |
    X_{1:t})`, the causal forward-algorithm posterior -- never the
    smoothed/backward-looking `predict_proba` or the globally-optimal
    Viterbi `decode`, both of which would leak future observations into
    the estimate at `timestamp`). `confidence` is that same posterior
    probability for `regime_id`. `transition_probability` is
    `P(S_{t+1} = regime_id | S_t = regime_id)` -- the model's own
    transition-matrix self-probability for the current regime, i.e. how
    "sticky" this regime call is expected to be, not a prediction about
    what regime comes next. `model_version` and `feature_pipeline_version`
    together make a regime call traceable back to exactly which trained
    model and which `FeatureVector` contract version produced it -- see
    `features.feature_vector.Provenance` for the same reasoning applied to
    features themselves.
    """

    timestamp: datetime
    symbol: str
    regime_id: int
    confidence: float
    transition_probability: float
    model_version: str
    feature_pipeline_version: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.regime_id < 0:
            raise ValueError(f"regime_id must be >= 0, got {self.regime_id}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if not 0.0 <= self.transition_probability <= 1.0:
            raise ValueError(
                f"transition_probability must be in [0, 1], got {self.transition_probability}"
            )

    def to_dict(self) -> dict[str, Any]:
        """The full contract, JSON-serializable. `metadata` is copied
        shallowly, not deep-converted -- a tuple value (e.g.
        `regime_probabilities`) round-trips through JSON as a list, the
        same way `ModelMetadata.feature_versions` already does.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "regime_id": self.regime_id,
            "confidence": self.confidence,
            "transition_probability": self.transition_probability,
            "model_version": self.model_version,
            "feature_pipeline_version": self.feature_pipeline_version,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RegimeState:
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            symbol=data["symbol"],
            regime_id=data["regime_id"],
            confidence=data["confidence"],
            transition_probability=data["transition_probability"],
            model_version=data["model_version"],
            feature_pipeline_version=data["feature_pipeline_version"],
            metadata=dict(data["metadata"]),
        )


@dataclass(frozen=True)
class TrainedModel:
    """Internal to `hmm` -- one fitted `GaussianHMM` plus the training
    statistics `selector.py`/`persistence.py` need. Constructed by
    `trainer.train`, consumed by `selector.py`, `inference.py`, and
    `persistence.py`; never returned from `RegimeService`'s public API.
    """

    model: GaussianHMM
    n_states: int
    covariance_type: str
    random_state: int
    log_likelihood: float
    converged: bool
    n_iter_used: int
    n_samples: int
    n_features: int


@dataclass(frozen=True)
class ModelMetadata:
    """Everything `persistence.py` writes to `metadata.json` -- a typed
    view of Work Package 7's required fields, rather than an untyped
    dict assembled ad hoc at each call site.
    """

    model_version: str
    symbol: str
    feature_pipeline_version: str
    feature_names: tuple[str, ...]
    feature_versions: Mapping[str, int]
    training_window_start: datetime
    training_window_end: datetime
    n_states: int
    covariance_type: str
    random_state: int
    selection_criterion: str
    bic: float
    aic: float
    log_likelihood: float
    n_samples: int
    converged: bool
    n_iter_used: int
    trained_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.training_window_start, "training_window_start")
        require_utc(self.training_window_end, "training_window_end")
        require_utc(self.trained_at, "trained_at")
        if self.training_window_start > self.training_window_end:
            raise ValueError(
                "training_window_start must be <= training_window_end, got "
                f"{self.training_window_start!r} > {self.training_window_end!r}"
            )
        if not self.feature_names:
            raise ValueError("feature_names must not be empty")
        if set(self.feature_versions) != set(self.feature_names):
            raise ValueError(
                "feature_versions must cover exactly feature_names; got "
                f"{sorted(self.feature_versions)}, expected {sorted(self.feature_names)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "symbol": self.symbol,
            "feature_pipeline_version": self.feature_pipeline_version,
            "feature_names": list(self.feature_names),
            "feature_versions": dict(self.feature_versions),
            "training_window_start": self.training_window_start.isoformat(),
            "training_window_end": self.training_window_end.isoformat(),
            "n_states": self.n_states,
            "covariance_type": self.covariance_type,
            "random_state": self.random_state,
            "selection_criterion": self.selection_criterion,
            "bic": self.bic,
            "aic": self.aic,
            "log_likelihood": self.log_likelihood,
            "n_samples": self.n_samples,
            "converged": self.converged,
            "n_iter_used": self.n_iter_used,
            "trained_at": self.trained_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelMetadata:
        return cls(
            model_version=data["model_version"],
            symbol=data["symbol"],
            feature_pipeline_version=data["feature_pipeline_version"],
            feature_names=tuple(data["feature_names"]),
            feature_versions=dict(data["feature_versions"]),
            training_window_start=datetime.fromisoformat(data["training_window_start"]),
            training_window_end=datetime.fromisoformat(data["training_window_end"]),
            n_states=data["n_states"],
            covariance_type=data["covariance_type"],
            random_state=data["random_state"],
            selection_criterion=data["selection_criterion"],
            bic=data["bic"],
            aic=data["aic"],
            log_likelihood=data["log_likelihood"],
            n_samples=data["n_samples"],
            converged=data["converged"],
            n_iter_used=data["n_iter_used"],
            trained_at=datetime.fromisoformat(data["trained_at"]),
        )


__all__ = ["ModelMetadata", "RegimeState", "TrainedModel"]
