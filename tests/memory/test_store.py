"""Tests for `memory.store`: `InMemoryExperienceStore` and
`JsonlExperienceStore` -- Phase A's sole deliverable. No learning is
exercised here; these tests exist to prove serialization, replay
compatibility, and deterministic storage before Phase B (the bandit)
is built on top."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from memory.exceptions import CorruptExperienceLogError
from memory.models import ExperienceRecord
from memory.store import InMemoryExperienceStore, JsonlExperienceStore

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _record(**overrides: object) -> ExperienceRecord:
    defaults: dict[str, object] = {
        "symbol": "TEST",
        "strategy_id": "growth_v1",
        "regime_id": 0,
        "production_allocation": 0.7,
        "realized_pnl": 100.0,
        "realized_pnl_pct": 0.1,
        "won": True,
        "entry_timestamp": T0,
        "exit_timestamp": T0 + timedelta(days=5),
        "source_run_id": "run-1",
        "metadata": {},
    }
    defaults.update(overrides)
    if "holding_period" not in overrides:
        defaults["holding_period"] = defaults["exit_timestamp"] - defaults["entry_timestamp"]  # type: ignore[operator]
    return ExperienceRecord(**defaults)  # type: ignore[arg-type]


class TestInMemoryExperienceStore:
    def test_starts_empty(self) -> None:
        store = InMemoryExperienceStore()
        assert len(store) == 0
        assert store.for_context(strategy_id="growth_v1", regime_id=0) == ()

    def test_append_increases_length(self) -> None:
        store = InMemoryExperienceStore()
        store.append(_record())
        store.append(_record(symbol="OTHER"))
        assert len(store) == 2

    def test_for_context_filters_by_strategy_and_regime(self) -> None:
        store = InMemoryExperienceStore()
        matching = _record(strategy_id="growth_v1", regime_id=1)
        other_strategy = _record(strategy_id="bear_v1", regime_id=1)
        other_regime = _record(strategy_id="growth_v1", regime_id=2)
        store.append(matching)
        store.append(other_strategy)
        store.append(other_regime)
        result = store.for_context(strategy_id="growth_v1", regime_id=1)
        assert result == (matching,)

    def test_for_context_preserves_append_order(self) -> None:
        store = InMemoryExperienceStore()
        first = _record(source_run_id="run-1")
        second = _record(source_run_id="run-2")
        store.append(first)
        store.append(second)
        result = store.for_context(strategy_id="growth_v1", regime_id=0)
        assert result == (first, second)

    def test_no_mutation_method_exists(self) -> None:
        store = InMemoryExperienceStore()
        assert not hasattr(store, "remove")
        assert not hasattr(store, "clear")
        assert not hasattr(store, "pop")


class TestJsonlExperienceStore:
    def test_load_on_missing_file_starts_empty(self, tmp_path: Path) -> None:
        store = JsonlExperienceStore.load(tmp_path / "does_not_exist.jsonl")
        assert len(store) == 0

    def test_append_persists_to_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "experience.jsonl"
        store = JsonlExperienceStore.load(path)
        store.append(_record())
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_append_is_append_only_on_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "experience.jsonl"
        store = JsonlExperienceStore.load(path)
        store.append(_record(source_run_id="run-1"))
        store.append(_record(source_run_id="run-2"))
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_reload_reconstructs_identical_state(self, tmp_path: Path) -> None:
        path = tmp_path / "experience.jsonl"
        original = JsonlExperienceStore.load(path)
        records = [_record(source_run_id=f"run-{i}") for i in range(5)]
        for record in records:
            original.append(record)

        reloaded = JsonlExperienceStore.load(path)
        assert len(reloaded) == len(original) == 5
        assert reloaded.for_context(strategy_id="growth_v1", regime_id=0) == tuple(records)

    def test_reload_preserves_context_filtering(self, tmp_path: Path) -> None:
        path = tmp_path / "experience.jsonl"
        store = JsonlExperienceStore.load(path)
        store.append(_record(strategy_id="growth_v1", regime_id=0))
        store.append(_record(strategy_id="bear_v1", regime_id=0))

        reloaded = JsonlExperienceStore.load(path)
        assert len(reloaded.for_context(strategy_id="growth_v1", regime_id=0)) == 1
        assert len(reloaded.for_context(strategy_id="bear_v1", regime_id=0)) == 1

    def test_append_output_is_byte_for_byte_deterministic(self, tmp_path: Path) -> None:
        path_a = tmp_path / "a.jsonl"
        path_b = tmp_path / "b.jsonl"
        records = [_record(source_run_id=f"run-{i}") for i in range(3)]

        store_a = JsonlExperienceStore.load(path_a)
        store_b = JsonlExperienceStore.load(path_b)
        for record in records:
            store_a.append(record)
            store_b.append(record)

        assert path_a.read_text(encoding="utf-8") == path_b.read_text(encoding="utf-8")

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "experience.jsonl"
        store = JsonlExperienceStore.load(path)
        store.append(_record())
        assert path.exists()

    def test_load_raises_on_corrupt_line(self, tmp_path: Path) -> None:
        path = tmp_path / "experience.jsonl"
        path.write_text("not valid json\n", encoding="utf-8")
        with pytest.raises(CorruptExperienceLogError, match="not a valid ExperienceRecord"):
            JsonlExperienceStore.load(path)

    def test_load_raises_on_line_missing_required_field(self, tmp_path: Path) -> None:
        path = tmp_path / "experience.jsonl"
        path.write_text('{"symbol": "TEST"}\n', encoding="utf-8")
        with pytest.raises(CorruptExperienceLogError, match="not a valid ExperienceRecord"):
            JsonlExperienceStore.load(path)

    def test_load_skips_blank_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "experience.jsonl"
        store = JsonlExperienceStore.load(path)
        store.append(_record())
        with path.open("a", encoding="utf-8") as f:
            f.write("\n")

        reloaded = JsonlExperienceStore.load(path)
        assert len(reloaded) == 1
