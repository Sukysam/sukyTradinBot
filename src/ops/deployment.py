"""Deployment validation and release-artifact verification.

`validate_deployment` checks that a `DeploymentInfo` actually describes
the `RuntimeContext` it's paired with (same `version`/`git_commit`) --
drift between "what we say we're deploying" and "what's actually
running" must be caught before a release proceeds, not discovered
after. `ReleaseManifest`/`verify_release_manifest` check that the
artifacts being shipped match what was recorded at build time, via
SHA-256 checksums -- catches a corrupted or substituted build artifact
before it reaches `deployment_environment`.

No CI/CD platform integration: no GitHub Actions "deploy" workflow, no
Kubernetes manifest, no Terraform. No deployment target has been chosen
for this platform (only a `Dockerfile`/`docker-compose.yml` exist,
which build/run a container -- neither is a deployment target). Wiring
this mechanism to a real release pipeline is deliberately deferred,
same "no backend chosen yet" reasoning ADR-023/ADR-024 already gave for
`ops.tracing` and `ops.secrets`; see ADR-025.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ops.exceptions import DeploymentValidationError
from ops.models import DeploymentInfo, RuntimeContext
from ops.validation import ValidationResult


@dataclass(frozen=True)
class ReleaseManifest:
    """What a release is supposed to contain: one `DeploymentInfo` plus
    the expected SHA-256 checksum of every artifact being shipped."""

    deployment_info: DeploymentInfo
    artifact_checksums: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.artifact_checksums:
            raise ValueError("artifact_checksums must not be empty")


def compute_checksum(path: Path) -> str:
    """Return the SHA-256 hex digest of the file at `path`."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_release_manifest(
    manifest: ReleaseManifest, actual_checksums: Mapping[str, str]
) -> ValidationResult:
    """Compare `manifest.artifact_checksums` against `actual_checksums`
    (typically produced by calling `compute_checksum` on each real
    artifact). Collects every mismatch/missing artifact in one pass."""
    errors: list[str] = []
    for name, expected in manifest.artifact_checksums.items():
        actual = actual_checksums.get(name)
        if actual is None:
            errors.append(f"missing artifact: {name}")
        elif actual != expected:
            errors.append(f"checksum mismatch for {name}: expected {expected}, got {actual}")
    return ValidationResult(valid=not errors, errors=tuple(errors))


def validate_deployment(runtime: RuntimeContext, deployment: DeploymentInfo) -> ValidationResult:
    """Check that `deployment` describes the same build `runtime` is
    running -- `version` and `git_commit` must match."""
    errors: list[str] = []
    if runtime.platform_info.version != deployment.version:
        errors.append(
            f"version mismatch: runtime={runtime.platform_info.version!r} "
            f"deployment={deployment.version!r}"
        )
    if runtime.platform_info.git_commit != deployment.git_commit:
        errors.append(
            f"git_commit mismatch: runtime={runtime.platform_info.git_commit!r} "
            f"deployment={deployment.git_commit!r}"
        )
    return ValidationResult(valid=not errors, errors=tuple(errors))


def require_valid_deployment(result: ValidationResult) -> None:
    """Raise `DeploymentValidationError` unless `result.valid`."""
    if not result.valid:
        raise DeploymentValidationError("; ".join(result.errors))


__all__ = [
    "ReleaseManifest",
    "compute_checksum",
    "require_valid_deployment",
    "validate_deployment",
    "verify_release_manifest",
]
