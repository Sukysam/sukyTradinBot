from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.io import atomic_write_json, read_json_or_default


def test_atomic_write_json_creates_file_with_expected_content(tmp_path: Path) -> None:
    path = tmp_path / "state.json"

    atomic_write_json(path, {"b": 2, "a": 1})

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}


def test_atomic_write_json_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "state.json"

    atomic_write_json(path, {"x": 1})

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == {"x": 1}


def test_atomic_write_json_overwrites_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"old": true}', encoding="utf-8")

    atomic_write_json(path, {"new": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}


def test_atomic_write_json_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    path = tmp_path / "state.json"

    atomic_write_json(path, {"a": 1})

    remaining = list(tmp_path.iterdir())
    assert remaining == [path]


def test_atomic_write_json_cleans_up_temp_file_on_failure(tmp_path: Path) -> None:
    path = tmp_path / "state.json"

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(path, {"bad": Unserializable()})

    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_read_json_or_default_returns_default_when_missing(tmp_path: Path) -> None:
    result = read_json_or_default(tmp_path / "missing.json", default={"fallback": True})
    assert result == {"fallback": True}


def test_read_json_or_default_reads_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    atomic_write_json(path, {"count": 42})

    assert read_json_or_default(path, default=None) == {"count": 42}


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "roundtrip.json"
    data = {"nested": {"list": [1, 2, 3]}, "flag": True}

    atomic_write_json(path, data)

    assert read_json_or_default(path, default=None) == data
