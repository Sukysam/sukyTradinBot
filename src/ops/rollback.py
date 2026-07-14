"""Rollback target selection over deployment history.

Structurally distinct from `ops.deployment`: everything in that module
validates one `DeploymentInfo` (or one `ReleaseManifest`) in isolation;
`select_rollback_target` operates over a *sequence* of prior
deployments, the same kind of "different input shape, different
module" split `orchestration.evaluation` used when it needed paired
history rather than a single decision.

`history` is expected oldest-first (the order deployments actually
happened in) -- the same convention a caller already has for granted
if it's the one appending to that history as deployments occur, so no
new ordering convention needs to be invented or documented elsewhere.
"""

from __future__ import annotations

from collections.abc import Sequence

from ops.exceptions import NoRollbackTargetError
from ops.models import DeploymentInfo


def select_rollback_target(
    history: Sequence[DeploymentInfo], *, current: DeploymentInfo
) -> DeploymentInfo | None:
    """Return the most recent deployment in `history` (oldest-first)
    that isn't `current` -- the "last known good" a rollback would
    restore. Returns `None` if no such deployment exists (e.g. `current`
    is the first deployment to its environment)."""
    for deployment in reversed(history):
        if deployment.deployment_id != current.deployment_id:
            return deployment
    return None


def require_rollback_target(target: DeploymentInfo | None) -> DeploymentInfo:
    """Raise `NoRollbackTargetError` if `target` is `None`; otherwise
    return it unchanged. A rollback attempted with nothing to roll back
    to must fail loudly, not silently proceed as a no-op."""
    if target is None:
        raise NoRollbackTargetError("no rollback target available in deployment history")
    return target


__all__ = ["require_rollback_target", "select_rollback_target"]
