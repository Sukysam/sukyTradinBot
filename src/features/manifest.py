"""Generates the machine-readable feature catalog from the registry.

The checked-in snapshot lives at `config/feature_manifest.yaml` — regenerate
it with `write_manifest` whenever a feature is added, changed, or removed,
and commit the result in the same change (per
docs/engineering-handbook/00_MASTER_CHARTER.md Definition of Done #5:
documentation ships with the code change that motivates it).
`tests/features/test_manifest.py` fails if the checked-in file drifts from
what the current registry would regenerate, so this can't go stale silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from features.registry import DEFAULT_REGISTRY, FeatureRegistry, FeatureSpec

MANIFEST_SCHEMA_VERSION = "1"


def _spec_to_dict(spec: FeatureSpec) -> dict[str, Any]:
    return {
        "category": spec.category.value,
        "version": spec.version,
        "lookback": spec.lookback,
        "dtype": spec.dtype,
        "uses_future_data": spec.uses_future_data,
        "depends_on": list(spec.depends_on),
        "consumers": list(spec.consumers),
        "description": spec.description,
    }


def build_manifest(registry: FeatureRegistry | None = None) -> dict[str, Any]:
    """The manifest as a plain dict, ready for `yaml.safe_dump` — also
    used directly by `test_manifest.py` to compare against the checked-in
    file without a round trip through the filesystem.
    """
    registry = registry or DEFAULT_REGISTRY
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "feature_count": len(registry),
        "features": {spec.name: _spec_to_dict(spec) for spec in registry.all()},
    }


def write_manifest(path: Path, registry: FeatureRegistry | None = None) -> None:
    manifest = build_manifest(registry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            manifest, f, sort_keys=False, default_flow_style=False, width=100, allow_unicode=True
        )


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    return loaded if isinstance(loaded, dict) else {}


__all__ = ["MANIFEST_SCHEMA_VERSION", "build_manifest", "load_manifest", "write_manifest"]
