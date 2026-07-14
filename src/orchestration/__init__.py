"""Signal Orchestration (Milestone 11).

Reconciles StrategyDecision (primary) against advisory LearningDecision
and NewsSignal input, producing a FinalDecision. See
docs/engineering-handbook/Architecture/ADR/ADR-020-FinalDecision-Contract.md.

Phase A (`arbitration.py`, `signals.py`): a single, deterministic
arbitration rule -- no execution, no broker, no risk. Phase B
(`interfaces.py`, `policies/`): four pluggable ArbitrationPolicy
implementations (SafetyFirst, Consensus, WeightedVote, Confidence)
behind one Protocol; `arbitrate` defaults to SafetyFirstPolicy for
backward compatibility with Phase A. Phase C (`evaluation.py`):
cross-signal reporting -- agreement rate, signal conflict rate,
strategy-vs-learner divergence, news alignment, orchestration
confidence, override frequency. Wiring FinalDecision into
risk.RiskService is not authorized by this milestone; see the Standards
doc's "Wiring is not yet authorized" section.
"""

from __future__ import annotations

from orchestration.arbitration import arbitrate
from orchestration.config import OrchestrationConfig
from orchestration.evaluation import evaluate, generate_evaluation_report
from orchestration.exceptions import MismatchedSignalError, OrchestrationError
from orchestration.interfaces import ArbitrationPolicy
from orchestration.models import ArbitrationOutcome, FinalDecision, SignalInput
from orchestration.policies import (
    ConfidencePolicy,
    ConsensusPolicy,
    SafetyFirstPolicy,
    WeightedVotePolicy,
)

__version__ = "0.1.0"

__all__ = [
    "ArbitrationOutcome",
    "ArbitrationPolicy",
    "ConfidencePolicy",
    "ConsensusPolicy",
    "FinalDecision",
    "MismatchedSignalError",
    "OrchestrationConfig",
    "OrchestrationError",
    "SafetyFirstPolicy",
    "SignalInput",
    "WeightedVotePolicy",
    "__version__",
    "arbitrate",
    "evaluate",
    "generate_evaluation_report",
]
