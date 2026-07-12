"""Filesystem utilities for durable state.

`docs/engineering-handbook/05_MEMORY_ENGINEER.md`'s coding standards call
for atomic writes ("write to a temp file and rename") before this system
has more than one writer process per state file. `atomic_write_json` is
that primitive, built now as foundation infrastructure so any future state
file (trade context, learning weights, equity tracking, or anything
unrelated to trading) gets the same crash-safety guarantee without
reimplementing it.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: Any, *, indent: int | None = 2) -> None:
    """Write `data` to `path` as JSON, atomically.

    Writes to a temporary file in the same directory as `path` (so the
    final `os.replace` is guaranteed to be an atomic rename on the same
    filesystem, never a cross-filesystem copy) and only then replaces the
    target. A process that crashes mid-write leaves either the old file or
    the new one intact — never a truncated or partially-written file.
    Creates parent directories if they don't already exist, matching the
    load-or-init pattern already used throughout this repository's state
    files.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def read_json_or_default(path: Path, default: Any) -> Any:
    """Read JSON from `path`, or return `default` if the file doesn't exist.

    Matches the load-or-init pattern already established by
    `EquityTracker.load_or_init` and `LearningEngine._load_weights`: a
    missing file means "first run," not an error. Callers for whom a
    missing file is itself meaningful (see `learning_engine.
    load_trade_contexts`'s deliberate `FileNotFoundError`) should not use
    this helper — read the file directly and let the exception propagate.
    """
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


__all__ = ["atomic_write_json", "read_json_or_default"]
