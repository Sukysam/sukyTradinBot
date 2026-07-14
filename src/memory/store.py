"""Concrete `memory.interfaces.ExperienceStore` implementations.

`InMemoryExperienceStore` is pure in-process, append-only. `JsonlExperienceStore`
is file-backed, append-only, and replay-loadable -- the durable equivalent
of the legacy `data/trade_context_db.json`
(see docs/engineering-handbook/05_MEMORY_ENGINEER.md), given a frozen
record shape and a one-line-per-record JSON Lines format instead of a
single mutable JSON blob.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from memory.exceptions import CorruptExperienceLogError
from memory.models import ExperienceRecord


def _context_key(strategy_id: str, regime_id: int) -> tuple[str, int]:
    return (strategy_id, regime_id)


class InMemoryExperienceStore:
    """Append-only, in-process `ExperienceStore`. No persistence --
    process-lifetime only. `JsonlExperienceStore` composes this rather
    than duplicating its indexing logic."""

    def __init__(self) -> None:
        self._records: list[ExperienceRecord] = []
        self._by_context: dict[tuple[str, int], list[ExperienceRecord]] = defaultdict(list)

    def append(self, record: ExperienceRecord) -> None:
        self._records.append(record)
        self._by_context[_context_key(record.strategy_id, record.regime_id)].append(record)

    def for_context(self, *, strategy_id: str, regime_id: int) -> Sequence[ExperienceRecord]:
        return tuple(self._by_context.get(_context_key(strategy_id, regime_id), ()))

    def __len__(self) -> int:
        return len(self._records)


class JsonlExperienceStore:
    """Append-only, file-backed `ExperienceStore` -- one `ExperienceRecord`
    per line, JSON-encoded with sorted keys for byte-for-byte deterministic
    output. Single-writer: like `data/trade_context_db.json` before it,
    this store assumes exactly one process appends to a given path at a
    time; concurrent writers are not guarded against here.

    Construct via `JsonlExperienceStore.load(path)`, which replays every
    existing line into memory, or starts empty if `path` doesn't exist yet
    -- a missing experience log is a legitimate first-run state, not an
    error, following the load-or-init pattern every other durable state
    file in this codebase uses (see
    docs/engineering-handbook/05_MEMORY_ENGINEER.md's coding standards).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._delegate = InMemoryExperienceStore()

    @classmethod
    def load(cls, path: Path) -> JsonlExperienceStore:
        store = cls(path)
        if not path.exists():
            return store
        with path.open("r", encoding="utf-8") as f:
            for line_number, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = ExperienceRecord.from_dict(json.loads(line))
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    raise CorruptExperienceLogError(
                        f"{path}:{line_number} is not a valid ExperienceRecord: {exc}"
                    ) from exc
                store._delegate.append(record)
        return store

    def append(self, record: ExperienceRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), sort_keys=True))
            f.write("\n")
        self._delegate.append(record)

    def for_context(self, *, strategy_id: str, regime_id: int) -> Sequence[ExperienceRecord]:
        return self._delegate.for_context(strategy_id=strategy_id, regime_id=regime_id)

    def __len__(self) -> int:
        return len(self._delegate)


__all__ = ["InMemoryExperienceStore", "JsonlExperienceStore"]
