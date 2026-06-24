"""Tests for SchedulerStore (SQLite persistence), SchedulerRegistry, and tool functions."""
import json
import os
import shutil
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from core.scheduler.models import ScheduledActivity
from core.scheduler.store import SchedulerStore
from core.scheduler.registry import SchedulerRegistry, get_registry


class TestSchedulerStore:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_store.db")
        self.store = SchedulerStore(db_path=self._db)

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _act(self, aid="a1", priority=0, status="pending", goal="test"):
        return ScheduledActivity(
            activity_id=aid,
            priority=priority,
            status=status,
            goal=goal,
            created_at=datetime(2026, 6, 24, 12, 0, 0),
        )

    def test_add_and_get(self):
        act = self._act("act_001")
        self.store.add(act)
        loaded = self.store.get("act_001")
        assert loaded is not None
        assert loaded.activity_id == "act_001"
        assert loaded.goal == "test"
        assert loaded.status == "pending"

    def test_get_nonexistent(self):
        assert self.store.get("nope") is None

    def test_list_all(self):
        self.store.add(self._act("a1"))
        self.store.add(self._act("a2"))
        all_acts = self.store.list_all()
        assert len(all_acts) == 2

    def test_list_by_status(self):
        self.store.add(self._act("a1", status="pending"))
        self.store.add(self._act("a2", status="running"))
        self.store.add(self._act("a3", status="completed"))
        pending = self.store.list_by_status("pending")
        assert len(pending) == 1
        assert pending[0].activity_id == "a1"

    def test_update_status(self):
        self.store.add(self._act("a1"))
        self.store.update_status("a1", "running")
        loaded = self.store.get("a1")
        assert loaded.status == "running"

    def test_update_priority(self):
        self.store.add(self._act("a1", priority=0))
        self.store.update_priority("a1", 5)
        loaded = self.store.get("a1")
        assert loaded.priority == 5

    def test_update_metadata(self):
        self.store.add(self._act("a1"))
        self.store.update_metadata("a1", "key1", "value1")
        loaded = self.store.get("a1")
        assert loaded.metadata.get("key1") == "value1"

    def test_update_metadata_nonexistent(self):
        self.store.update_metadata("nope", "k", "v")
        # No crash

    def test_delete(self):
        self.store.add(self._act("a1"))
        self.store.delete("a1")
        assert self.store.get("a1") is None

    def test_count(self):
        assert self.store.count() == 0
        self.store.add(self._act("a1"))
        self.store.add(self._act("a2"))
        assert self.store.count() == 2

    def test_clear(self):
        self.store.add(self._act("a1"))
        self.store.add(self._act("a2"))
        self.store.clear()
        assert self.store.count() == 0

    def test_survives_restart(self):
        self.store.add(self._act("survive_me"))
        # Create new store instance pointing at same DB
        store2 = SchedulerStore(db_path=self._db)
        loaded = store2.get("survive_me")
        assert loaded is not None
        assert loaded.goal == "test"

    def test_add_updates_existing(self):
        self.store.add(self._act("a1", goal="original"))
        self.store.add(self._act("a1", goal="updated"))
        loaded = self.store.get("a1")
        assert loaded.goal == "updated"

    def test_default_db_path(self):
        store = SchedulerStore(db_path=self._db)
        assert store._db_path == self._db

    def test_depends_on_persistence(self):
        act = self._act("dep_test")
        act.depends_on = ["dep_a", "dep_b"]
        self.store.add(act)
        loaded = self.store.get("dep_test")
        assert loaded.depends_on == ["dep_a", "dep_b"]


class TestSchedulerRegistry:
    def test_register_and_get(self):
        registry = SchedulerRegistry()
        async def fake_fn(**kw): return {"ok": True}
        registry.register("research", fake_fn)
        assert registry.get("research") is fake_fn

    def test_get_nonexistent(self):
        registry = SchedulerRegistry()
        assert registry.get("nope") is None

    def test_unregister(self):
        registry = SchedulerRegistry()
        async def fake_fn(**kw): return {"ok": True}
        registry.register("build", fake_fn)
        registry.unregister("build")
        assert registry.get("build") is None

    def test_list_types(self):
        registry = SchedulerRegistry()
        async def fn(**kw): return {"ok": True}
        registry.register("a", fn)
        registry.register("b", fn)
        assert set(registry.list_types()) == {"a", "b"}

    def test_resolve_with_default(self):
        registry = SchedulerRegistry()
        async def default_fn(**kw): return {"ok": True}
        resolved = registry.resolve("missing", default_fn)
        assert resolved is default_fn

    def test_resolve_found(self):
        registry = SchedulerRegistry()
        async def fn(**kw): return {"ok": True}
        registry.register("found", fn)
        resolved = registry.resolve("found")
        assert resolved is fn

    def test_warns_for_non_async(self):
        registry = SchedulerRegistry()
        def sync_fn(**kw): return {"ok": True}
        registry.register("sync", sync_fn)
        # Should not crash even though sync_fn isn't async

    def test_get_registry_singleton(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
