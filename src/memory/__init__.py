"""Adaptive Learning / Memory Loop (Milestone 9) -- shadow mode only.

Records what the learner would have recommended for every real
`StrategyDecision` it observes, without ever influencing `strategy`,
`risk`, or `execution`. See
docs/engineering-handbook/Architecture/ADR/ADR-016-LearningDecision-Contract.md
and
docs/engineering-handbook/Architecture/ADR/ADR-017-Memory-Loop-Design.md.

Phase A (`store.py`): an append-only Experience Store, no learning yet.
Phase B (`bandit.py`, `service.py`): a contextual Thompson Sampling bandit
over `(strategy_id, regime_id)`, producing shadow `LearningDecision`s.
Phase C (`evaluation.py`): comparison reporting between production and
shadow recommendations -- still no production influence.
"""

from __future__ import annotations

from memory.bandit import BetaArm, ThompsonSamplingPolicy, context_key
from memory.config import MemoryConfig
from memory.evaluation import evaluate, generate_evaluation_report
from memory.exceptions import CorruptExperienceLogError, MemoryLoopError
from memory.models import ExperienceRecord, LearningDecision
from memory.service import MemoryService
from memory.store import InMemoryExperienceStore, JsonlExperienceStore

__version__ = "0.1.0"

__all__ = [
    "BetaArm",
    "CorruptExperienceLogError",
    "ExperienceRecord",
    "InMemoryExperienceStore",
    "JsonlExperienceStore",
    "LearningDecision",
    "MemoryConfig",
    "MemoryLoopError",
    "MemoryService",
    "ThompsonSamplingPolicy",
    "__version__",
    "context_key",
    "evaluate",
    "generate_evaluation_report",
]
