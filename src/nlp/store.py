"""Concrete `nlp.interfaces.NewsItemStore` implementations.

`InMemoryNewsItemStore` is pure in-process. `JsonlNewsItemStore` is
file-backed and replay-loadable, mirroring `memory.store.
JsonlExperienceStore`'s single-writer, load-or-init, sorted-key-JSON-
per-line design -- the same durable-log pattern applied to a second
package.
"""

from __future__ import annotations

import json
from pathlib import Path

from nlp.exceptions import CorruptNewsLogError
from nlp.models import NewsItem


def _dedup_key(item: NewsItem) -> tuple[str, str]:
    return (item.source, item.source_id)


class InMemoryNewsItemStore:
    """Deduplicating, in-process `NewsItemStore`. No persistence --
    process-lifetime only. `JsonlNewsItemStore` composes this rather than
    duplicating its dedup-index logic."""

    def __init__(self) -> None:
        self._items: list[NewsItem] = []
        self._seen: set[tuple[str, str]] = set()

    def add(self, item: NewsItem) -> bool:
        key = _dedup_key(item)
        if key in self._seen:
            return False
        self._seen.add(key)
        self._items.append(item)
        return True

    def all(self) -> tuple[NewsItem, ...]:
        return tuple(self._items)

    def __len__(self) -> int:
        return len(self._items)


class JsonlNewsItemStore:
    """Append-only, file-backed `NewsItemStore` -- one `NewsItem` per
    line, JSON-encoded with sorted keys for byte-for-byte deterministic
    output. Single-writer, same assumption `memory.store.
    JsonlExperienceStore` makes. A duplicate `add` call is a no-op: it
    neither appends a new line nor re-writes the existing one.

    Construct via `JsonlNewsItemStore.load(path)`, which replays every
    existing line into memory, or starts empty if `path` doesn't exist
    yet -- a missing news log is a legitimate first-run state.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._delegate = InMemoryNewsItemStore()

    @classmethod
    def load(cls, path: Path) -> JsonlNewsItemStore:
        store = cls(path)
        if not path.exists():
            return store
        with path.open("r", encoding="utf-8") as f:
            for line_number, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    item = NewsItem.from_dict(json.loads(line))
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    raise CorruptNewsLogError(
                        f"{path}:{line_number} is not a valid NewsItem: {exc}"
                    ) from exc
                store._delegate.add(item)
        return store

    def add(self, item: NewsItem) -> bool:
        if not self._delegate.add(item):
            return False
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item.to_dict(), sort_keys=True))
            f.write("\n")
        return True

    def all(self) -> tuple[NewsItem, ...]:
        return self._delegate.all()

    def __len__(self) -> int:
        return len(self._delegate)


__all__ = ["InMemoryNewsItemStore", "JsonlNewsItemStore"]
