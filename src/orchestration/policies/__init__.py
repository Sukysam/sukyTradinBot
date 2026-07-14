"""Four `orchestration.interfaces.ArbitrationPolicy` implementations,
each a genuinely distinct arbitration mechanism behind the same
interface -- `orchestration.arbitration.arbitrate` (and any future
`SignalOrchestrator` service) delegates to whichever is selected, never
hardcoding the algorithm itself. See ADR-021 for why these four and not
others, and for each policy's own docstring for its specific mechanism.
"""

from __future__ import annotations

from orchestration.policies.confidence import ConfidencePolicy
from orchestration.policies.consensus import ConsensusPolicy
from orchestration.policies.safety_first import SafetyFirstPolicy
from orchestration.policies.weighted_vote import WeightedVotePolicy

__all__ = [
    "ConfidencePolicy",
    "ConsensusPolicy",
    "SafetyFirstPolicy",
    "WeightedVotePolicy",
]
