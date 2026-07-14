"""Tests for `ops.deployment`: `ReleaseManifest`, `compute_checksum`,
`verify_release_manifest`, `validate_deployment`, and
`require_valid_deployment`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ops.deployment import (
    ReleaseManifest,
    compute_checksum,
    require_valid_deployment,
    validate_deployment,
    verify_release_manifest,
)
from ops.exceptions import DeploymentValidationError
from ops.models import DeploymentInfo, PlatformInfo, RuntimeContext
from ops.validation import ValidationResult

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _deployment(**overrides: object) -> DeploymentInfo:
    defaults: dict[str, object] = {
        "version": "0.12.0",
        "git_commit": "abc1234",
        "build_time": T0,
        "deployment_environment": "production",
        "deployment_id": "deploy-001",
    }
    defaults.update(overrides)
    return DeploymentInfo(**defaults)  # type: ignore[arg-type]


def _runtime() -> RuntimeContext:
    info = PlatformInfo(
        version="0.12.0",
        git_commit="abc1234",
        build_time=T0,
        python_version="3.9.6",
    )
    return RuntimeContext(platform_info=info, environment="production", startup_time=T0)


class TestReleaseManifest:
    def test_valid_manifest_constructs(self) -> None:
        manifest = ReleaseManifest(
            deployment_info=_deployment(), artifact_checksums={"app.tar.gz": "abc123"}
        )
        assert manifest.artifact_checksums["app.tar.gz"] == "abc123"

    def test_rejects_empty_artifact_checksums(self) -> None:
        with pytest.raises(ValueError, match="artifact_checksums"):
            ReleaseManifest(deployment_info=_deployment(), artifact_checksums={})


class TestComputeChecksum:
    def test_matches_known_sha256(self, tmp_path: Path) -> None:
        path = tmp_path / "artifact.txt"
        path.write_bytes(b"hello world")
        assert (
            compute_checksum(path)
            == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        )

    def test_same_content_produces_same_checksum(self, tmp_path: Path) -> None:
        path = tmp_path / "artifact.txt"
        path.write_bytes(b"hello world")
        assert compute_checksum(path) == compute_checksum(path)

    def test_different_content_produces_different_checksum(self, tmp_path: Path) -> None:
        path_a = tmp_path / "a.txt"
        path_b = tmp_path / "b.txt"
        path_a.write_bytes(b"content a")
        path_b.write_bytes(b"content b")
        assert compute_checksum(path_a) != compute_checksum(path_b)


class TestVerifyReleaseManifest:
    def test_valid_when_checksums_match(self) -> None:
        manifest = ReleaseManifest(
            deployment_info=_deployment(), artifact_checksums={"app.tar.gz": "abc123"}
        )
        result = verify_release_manifest(manifest, {"app.tar.gz": "abc123"})
        assert result.valid is True

    def test_invalid_when_checksum_mismatches(self) -> None:
        manifest = ReleaseManifest(
            deployment_info=_deployment(), artifact_checksums={"app.tar.gz": "abc123"}
        )
        result = verify_release_manifest(manifest, {"app.tar.gz": "different"})
        assert result.valid is False
        assert any("checksum mismatch" in error for error in result.errors)

    def test_invalid_when_artifact_missing(self) -> None:
        manifest = ReleaseManifest(
            deployment_info=_deployment(), artifact_checksums={"app.tar.gz": "abc123"}
        )
        result = verify_release_manifest(manifest, {})
        assert result.valid is False
        assert any("missing artifact" in error for error in result.errors)

    def test_collects_multiple_errors(self) -> None:
        manifest = ReleaseManifest(
            deployment_info=_deployment(),
            artifact_checksums={"a.tar.gz": "aaa", "b.tar.gz": "bbb"},
        )
        result = verify_release_manifest(manifest, {"a.tar.gz": "wrong"})
        assert len(result.errors) == 2


class TestValidateDeployment:
    def test_valid_when_version_and_commit_match(self) -> None:
        result = validate_deployment(_runtime(), _deployment())
        assert result.valid is True

    def test_invalid_when_version_mismatches(self) -> None:
        result = validate_deployment(_runtime(), _deployment(version="0.13.0"))
        assert result.valid is False
        assert any("version mismatch" in error for error in result.errors)

    def test_invalid_when_git_commit_mismatches(self) -> None:
        result = validate_deployment(_runtime(), _deployment(git_commit="def5678"))
        assert result.valid is False
        assert any("git_commit mismatch" in error for error in result.errors)

    def test_collects_both_mismatches(self) -> None:
        result = validate_deployment(
            _runtime(), _deployment(version="0.13.0", git_commit="def5678")
        )
        assert len(result.errors) == 2


class TestRequireValidDeployment:
    def test_does_not_raise_when_valid(self) -> None:
        require_valid_deployment(ValidationResult(valid=True, errors=()))

    def test_raises_when_invalid(self) -> None:
        result = ValidationResult(valid=False, errors=("version mismatch",))
        with pytest.raises(DeploymentValidationError, match="version mismatch"):
            require_valid_deployment(result)
