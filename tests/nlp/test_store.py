"""Tests for `nlp.store`: `InMemoryNewsItemStore` and
`JsonlNewsItemStore` -- Phase A's sole deliverable alongside `models.py`
and `normalize.py`. No sentiment scoring is exercised here."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from nlp.exceptions import CorruptNewsLogError
from nlp.models import NewsItem
from nlp.store import InMemoryNewsItemStore, JsonlNewsItemStore

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _item(**overrides: object) -> NewsItem:
    defaults: dict[str, object] = {
        "source_id": "12345",
        "source": "alpaca_news",
        "headline": "Fed holds rates steady",
        "summary": "",
        "symbols": ("AAPL",),
        "published_at": T0,
    }
    defaults.update(overrides)
    return NewsItem(**defaults)  # type: ignore[arg-type]


class TestInMemoryNewsItemStore:
    def test_starts_empty(self) -> None:
        store = InMemoryNewsItemStore()
        assert len(store) == 0
        assert store.all() == ()

    def test_add_returns_true_for_new_item(self) -> None:
        store = InMemoryNewsItemStore()
        assert store.add(_item()) is True
        assert len(store) == 1

    def test_add_returns_false_for_duplicate_source_id(self) -> None:
        store = InMemoryNewsItemStore()
        store.add(_item(source_id="12345"))
        assert store.add(_item(source_id="12345", headline="Different headline")) is False
        assert len(store) == 1

    def test_same_source_id_different_source_is_not_a_duplicate(self) -> None:
        store = InMemoryNewsItemStore()
        store.add(_item(source="alpaca_news", source_id="1"))
        assert store.add(_item(source="other_feed", source_id="1")) is True
        assert len(store) == 2

    def test_all_preserves_first_add_order(self) -> None:
        store = InMemoryNewsItemStore()
        first = _item(source_id="1")
        second = _item(source_id="2")
        store.add(first)
        store.add(second)
        assert store.all() == (first, second)

    def test_no_mutation_method_exists(self) -> None:
        store = InMemoryNewsItemStore()
        assert not hasattr(store, "remove")
        assert not hasattr(store, "clear")


class TestJsonlNewsItemStore:
    def test_load_on_missing_file_starts_empty(self, tmp_path: Path) -> None:
        store = JsonlNewsItemStore.load(tmp_path / "does_not_exist.jsonl")
        assert len(store) == 0

    def test_add_persists_to_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "news.jsonl"
        store = JsonlNewsItemStore.load(path)
        store.add(_item())
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_duplicate_add_does_not_write_a_second_line(self, tmp_path: Path) -> None:
        path = tmp_path / "news.jsonl"
        store = JsonlNewsItemStore.load(path)
        store.add(_item(source_id="1"))
        store.add(_item(source_id="1", headline="Different headline"))
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_reload_reconstructs_identical_state(self, tmp_path: Path) -> None:
        path = tmp_path / "news.jsonl"
        original = JsonlNewsItemStore.load(path)
        items = [_item(source_id=str(i)) for i in range(5)]
        for item in items:
            original.add(item)

        reloaded = JsonlNewsItemStore.load(path)
        assert len(reloaded) == len(original) == 5
        assert reloaded.all() == tuple(items)

    def test_reload_preserves_dedup_state(self, tmp_path: Path) -> None:
        path = tmp_path / "news.jsonl"
        store = JsonlNewsItemStore.load(path)
        store.add(_item(source_id="1"))

        reloaded = JsonlNewsItemStore.load(path)
        assert reloaded.add(_item(source_id="1", headline="Different headline")) is False
        assert len(reloaded) == 1

    def test_add_output_is_byte_for_byte_deterministic(self, tmp_path: Path) -> None:
        path_a = tmp_path / "a.jsonl"
        path_b = tmp_path / "b.jsonl"
        items = [_item(source_id=str(i)) for i in range(3)]

        store_a = JsonlNewsItemStore.load(path_a)
        store_b = JsonlNewsItemStore.load(path_b)
        for item in items:
            store_a.add(item)
            store_b.add(item)

        assert path_a.read_text(encoding="utf-8") == path_b.read_text(encoding="utf-8")

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "news.jsonl"
        store = JsonlNewsItemStore.load(path)
        store.add(_item())
        assert path.exists()

    def test_load_raises_on_corrupt_line(self, tmp_path: Path) -> None:
        path = tmp_path / "news.jsonl"
        path.write_text("not valid json\n", encoding="utf-8")
        with pytest.raises(CorruptNewsLogError, match="not a valid NewsItem"):
            JsonlNewsItemStore.load(path)

    def test_load_raises_on_line_missing_required_field(self, tmp_path: Path) -> None:
        path = tmp_path / "news.jsonl"
        path.write_text('{"source_id": "1"}\n', encoding="utf-8")
        with pytest.raises(CorruptNewsLogError, match="not a valid NewsItem"):
            JsonlNewsItemStore.load(path)

    def test_load_skips_blank_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "news.jsonl"
        store = JsonlNewsItemStore.load(path)
        store.add(_item())
        with path.open("a", encoding="utf-8") as f:
            f.write("\n")

        reloaded = JsonlNewsItemStore.load(path)
        assert len(reloaded) == 1
