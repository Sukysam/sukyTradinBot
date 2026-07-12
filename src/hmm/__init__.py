"""HMM & Regime Detection (Milestone 4).

The only public surface: `RegimeService`, `RegimeState`, and the
`config`/`exceptions` types needed to call it. `RegimeService` consumes
only `features.feature_vector.FeatureVector` and produces only
`RegimeState` -- it knows nothing about Alpaca, orders, strategies, risk,
memory, or NLP. See
docs/engineering-handbook/Architecture/ADR/ADR-006-RegimeState-Contract.md
and
docs/engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md.

`trainer`, `selector`, `inference`, `normalizer`, and `persistence` are
implementation modules -- callable directly for testing, but
`RegimeService` is the sanctioned entry point for anything outside this
package.
"""

from __future__ import annotations

from hmm.config import HMMConfig, SelectionConfig, SelectionCriterion, TrainingConfig
from hmm.exceptions import (
    ContractViolationError,
    HMMError,
    InsufficientDataError,
    ModelNotFittedError,
    PersistenceError,
    TrainingError,
)
from hmm.models import RegimeState
from hmm.service import RegimeService

__version__ = "0.1.0"

__all__ = [
    "ContractViolationError",
    "HMMConfig",
    "HMMError",
    "InsufficientDataError",
    "ModelNotFittedError",
    "PersistenceError",
    "RegimeService",
    "RegimeState",
    "SelectionConfig",
    "SelectionCriterion",
    "TrainingConfig",
    "TrainingError",
    "__version__",
]
