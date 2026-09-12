"""Unit tests for core.browser.procedural_memory (isolated sqlite db)."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from core.browser.procedural_memory import BrowserProceduralMemory


@pytest.fixture()
def memory(tmp_path):
    return BrowserProceduralMemory(db_path=str(tmp_path / "memory.db"), ttl_days=14.0)


STEPS = [
    {"step": 1, "action": "open repository page"},
    {"step": 2, "action": "click New", "selector": "a[href='/new']"},
    {"step": 3, "action": "enter repository name", "selector": "#repository_name"},
    {"step": 4, "action": "select visibility"},
    {"step": 5, "action": "create repository"},
    {"step": 6, "action": "verify repository URL exists"},
]


class TestRecordAndGet:
    def test_record_new_procedure(self, memory):
        proc_id = memory.record("https://github.com", "create repository", STEPS, success=True, selectors={"new_button": "a[href='/new']"})
        assert proc_id
        proc = memory.get("github.com", "create repository")
        assert proc is not None
        assert proc["site"] == "github.com"
        assert proc["task"] == "create_repository"
        assert len(proc["steps"]) == 6
        assert proc["selectors"]["new_button"] == "a[href='/new']"
        assert proc["last_verified"] is not None
        assert proc["stale"] is False
        assert proc["usable"] is True

    def test_normalizes_www_and_case(self, memory):
        memory.record("https://WWW.GitHub.com/", "Create Repository", STEPS, success=True)
        proc = memory.get("github.com", "create repository")
        assert proc is not None

    def test_failure_does_not_overwrite_steps(self, memory):
        memory.record("github.com", "create repo", STEPS, success=True)
        memory.record("github.com", "create repo", [], success=False, failure_mode="New button not found")
        proc = memory.get("github.com", "create repo")
        assert len(proc["steps"]) == 6
        assert "New button not found" in proc["failure_modes"]
        assert proc["success_rate"] == 0.5

    def test_confidence_moves_with_outcomes(self, memory):
        memory.record("pypi.org", "search package", STEPS, success=True)
        base = memory.get("pypi.org", "search package")["confidence"]
        memory.record("pypi.org", "search package", STEPS, success=True)
        up = memory.get("pypi.org", "search package")["confidence"]
        memory.record("pypi.org", "search package", [], success=False, failure_mode="rate limited")
        down = memory.get("pypi.org", "search package")["confidence"]
        assert up > base > down


class TestFreshness:
    def test_stale_after_ttl(self, tmp_path):
        memory = BrowserProceduralMemory(db_path=str(tmp_path / "memory.db"), ttl_days=14.0)
        memory.record("example.com", "do thing", STEPS, success=True)
        # backdate last_verified beyond the TTL
        import sqlite3
        old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        conn = sqlite3.connect(memory._db_path)
        conn.execute("UPDATE browser_procedures SET last_verified = ? WHERE site = 'example.com'", (old,))
        conn.commit()
        conn.close()
        proc = memory.get("example.com", "do thing")
        assert proc["stale"] is True
        assert proc["usable"] is False
        assert proc["age_days"] > 14

    def test_unverified_procedure_not_usable(self, memory):
        memory.record("example.org", "flaky task", [], success=False, failure_mode="never worked")
        proc = memory.get("example.org", "flaky task")
        assert proc["usable"] is False
        assert proc["last_verified"] is None


class TestFindAndSummary:
    def test_find_by_substring(self, memory):
        memory.record("github.com", "create repo", STEPS, success=True)
        memory.record("gitlab.com", "create repo", STEPS, success=True)
        matches = memory.find("github")
        assert [m["site"] for m in matches] == ["github.com"]

    def test_summary_counts(self, memory):
        memory.record("a.com", "t1", STEPS, success=True)
        memory.record("b.com", "t2", [], success=False, failure_mode="x")
        summary = memory.summary()
        assert summary["procedures"] == 2
        assert summary["fresh"] == 1
        assert summary["stale"] == 1
        assert summary["usable"] == 1


class TestEpisodeMirror:
    def test_mirror_failure_is_swallowed(self, memory, monkeypatch):
        import core.browser.procedural_memory as pm
        def boom(*args, **kwargs):
            raise RuntimeError("memory facade offline")
        monkeypatch.setattr(pm, "_mirror_episode_target", boom, raising=False)
        # _mirror_episode imports memory facade lazily; a broken facade must not
        # break record().  Simulate by breaking the import.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "memory.memory_facade":
                raise RuntimeError("memory facade offline")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        proc_id = memory.record("example.net", "task", STEPS, success=True)
        assert proc_id  # record still succeeds
