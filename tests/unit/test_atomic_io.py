# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for core.atomic_io durability and crash-safety behavior."""
import json
from pathlib import Path

import pytest

from core.atomic_io import atomic_write_json, atomic_write_text


def _tmp_siblings(directory: Path, name: str) -> list:
    return list(directory.glob(f"{name}.tmp.*"))


def test_atomic_write_json_round_trips_object(tmp_path):
    target = tmp_path / "data.json"
    original = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}, "s": "héllo"}
    atomic_write_json(str(target), original)
    assert json.loads(target.read_text(encoding="utf-8")) == original


def test_atomic_write_json_honors_indent(tmp_path):
    target = tmp_path / "indented.json"
    atomic_write_json(str(target), {"a": 1}, indent=2)
    text = target.read_text(encoding="utf-8")
    assert "\n" in text
    assert text == json.dumps({"a": 1}, indent=2)


def test_atomic_write_json_creates_missing_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "data.json"
    atomic_write_json(str(target), {"ok": True})
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}


def test_atomic_write_json_fully_overwrites_longer_content(tmp_path):
    target = tmp_path / "data.json"
    atomic_write_json(str(target), {"k": "x" * 500})
    atomic_write_json(str(target), {"k": "short"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"k": "short"}
    assert target.read_text(encoding="utf-8") == json.dumps({"k": "short"})


def test_atomic_write_json_leaves_no_tmp_file(tmp_path):
    target = tmp_path / "data.json"
    atomic_write_json(str(target), {"a": 1})
    assert _tmp_siblings(tmp_path, "data.json") == []


def test_atomic_write_json_preserves_target_when_serialization_fails(tmp_path):
    target = tmp_path / "data.json"
    atomic_write_json(str(target), {"existing": "value"})
    before = target.read_text(encoding="utf-8")
    with pytest.raises(TypeError):
        atomic_write_json(str(target), {"bad": {1, 2, 3}})
    assert target.read_text(encoding="utf-8") == before


def test_atomic_write_text_round_trips(tmp_path):
    target = tmp_path / "note.txt"
    text = "line one\nline two\nunicode: héllo\n"
    atomic_write_text(str(target), text)
    assert target.read_text(encoding="utf-8") == text


def test_atomic_write_text_creates_missing_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "note.txt"
    atomic_write_text(str(target), "content")
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "content"


def test_atomic_write_text_fully_overwrites_longer_content(tmp_path):
    target = tmp_path / "note.txt"
    atomic_write_text(str(target), "x" * 500)
    atomic_write_text(str(target), "short")
    assert target.read_text(encoding="utf-8") == "short"


def test_atomic_write_text_leaves_no_tmp_file(tmp_path):
    target = tmp_path / "note.txt"
    atomic_write_text(str(target), "content")
    assert _tmp_siblings(tmp_path, "note.txt") == []


def test_atomic_write_text_preserves_target_when_replace_fails(tmp_path, monkeypatch):
    import os as os_mod
    target = tmp_path / "note.txt"
    atomic_write_text(str(target), "original content")
    before = target.read_text(encoding="utf-8")

    def boom(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(os_mod, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(str(target), "new content that never lands")
    assert target.read_text(encoding="utf-8") == before
