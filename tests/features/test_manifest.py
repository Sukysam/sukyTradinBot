from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from features.manifest import build_manifest, load_manifest, write_manifest
from features.registry import DEFAULT_REGISTRY

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "config" / "feature_manifest.yaml"


def test_build_manifest_covers_every_registered_feature() -> None:
    manifest = build_manifest()
    assert manifest["feature_count"] == len(DEFAULT_REGISTRY)
    assert set(manifest["features"]) == set(DEFAULT_REGISTRY.names())


def test_build_manifest_entries_have_required_fields() -> None:
    manifest = build_manifest()
    for name, entry in manifest["features"].items():
        for field in (
            "category",
            "version",
            "lookback",
            "dtype",
            "uses_future_data",
            "description",
        ):
            assert field in entry, f"{name} manifest entry missing {field!r}"
        assert entry["uses_future_data"] is False


def test_write_and_load_manifest_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    write_manifest(path)
    loaded = load_manifest(path)
    assert loaded == build_manifest()


def test_write_manifest_produces_valid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    write_manifest(path)
    with path.open() as f:
        raw = yaml.safe_load(f)
    assert raw["feature_count"] == len(DEFAULT_REGISTRY)


def test_checked_in_manifest_is_up_to_date() -> None:
    """Fails if `config/feature_manifest.yaml` drifts from what the
    current registry would regenerate — see manifest.py's module
    docstring: regenerate and commit it in the same change as any feature
    addition/removal/change, never let it go stale silently.
    """
    if not MANIFEST_PATH.exists():
        pytest.fail(
            f"{MANIFEST_PATH} does not exist. Generate it once via "
            "features.manifest.write_manifest(MANIFEST_PATH) and commit it."
        )
    checked_in = load_manifest(MANIFEST_PATH)
    current = build_manifest()
    assert checked_in == current, (
        f"{MANIFEST_PATH} is stale. Regenerate with "
        "features.manifest.write_manifest(Path('config/feature_manifest.yaml')) and commit."
    )
