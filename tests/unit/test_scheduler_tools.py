"""Tests for scheduler tool functions."""
import asyncio
import os
import shutil
import tempfile
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from core.activity.manager import ActivityManager
from core.activity.resume import ResumeEngine
from core.activity.storage import ActivityStore
from core.scheduler.queue import SchedulerQueue
from core.scheduler.scheduler import Scheduler
from core.scheduler.store import SchedulerStore


class TestSchedulerQueueExt:
    """Extended queue tests for new functionality (submit, cancel, set_priority)."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_queue_ext.db")
        self._store = ActivityStore(db_path=self._db)
        self._mgr = ActivityManager(store=self._store)
        self._sstore = SchedulerStore(db_path=self._db)
        self._queue = SchedulerQueue(self._mgr, store=self._sstore)

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_submit_adds_to_queue(self):
        act = self._queue.submit("sub_001", goal="Research topic")
        assert act.activity_id == "sub_001"
        assert act.goal == "Research topic"
        assert act.status == "pending"
        # Persisted
        loaded = self._sstore.get("sub_001")
        assert loaded is not None
        assert loaded.goal == "Research topic"

    def test_submit_with_priority_and_deps(self):
        act = self._queue.submit(
            "sub_002", goal="Build", priority=5,
            depends_on=["sub_001"],
            metadata={"tool_type": "build"},
        )
        assert act.priority == 5
        assert act.depends_on == ["sub_001"]
        assert act.metadata.get("tool_type") == "build"

    def test_cancel_pending_activity(self):
        self._queue.submit("cancel_me", goal="Cancel this")
        self._queue.refresh()
        result = self._queue.cancel("cancel_me")
        assert result is True
        assert self._queue.get_best() is None

    def test_cancel_nonexistent(self):
        result = self._queue.cancel("nope")
        assert result is False

    def test_cancel_running_ignored(self):
        self._queue.submit("run_me", goal="Running")
        self._queue.mark_running("run_me")
        result = self._queue.cancel("run_me")
        assert result is False

    def test_set_priority(self):
        self._queue.submit("prio_test", goal="Test")
        self._queue.set_priority("prio_test", 5)
        act = self._sstore.get("prio_test")
        assert act.priority == 5

    def test_set_priority_nonexistent(self):
        result = self._queue.set_priority("nope", 5)
        assert result is False

    def test_mark_running_persists(self):
        self._queue.submit("persist_run", goal="Run test")
        self._queue.refresh()
        self._queue.mark_running("persist_run")
        loaded = self._sstore.get("persist_run")
        assert loaded.status == "running"

    def test_mark_failed_persists(self):
        self._queue.submit("persist_fail", goal="Fail test")
        self._queue.refresh()
        self._queue.mark_failed("persist_fail")
        loaded = self._sstore.get("persist_fail")
        assert loaded.status == "failed"
        assert loaded.metadata.get("previous_status") == "failed"

    def test_mark_completed_persists(self):
        self._queue.submit("persist_done", goal="Done test")
        self._queue.refresh()
        self._queue.mark_completed("persist_done")
        loaded = self._sstore.get("persist_done")
        assert loaded.status == "completed"

    def test_get_best_returns_highest_score(self):
        self._queue.submit("low", goal="Low", priority=0)
        self._queue.submit("high", goal="High", priority=5)
        self._queue.refresh()
        best = self._queue.get_best()
        assert best is not None
        assert best.activity_id == "high"

    def test_deps_block(self):
        self._queue.submit("dep_a", goal="A")
        self._queue.submit("dep_b", goal="B", depends_on=["dep_a"])
        self._queue.refresh()
        # dep_b should be blocked until dep_a is completed
        assert len(self._queue.ready) == 1
        assert self._queue.ready[0].activity_id == "dep_a"
        assert len(self._queue.blocked) == 1

    def test_deps_unblock_after_complete(self):
        self._queue.submit("dep_a", goal="A")
        self._queue.submit("dep_b", goal="B", depends_on=["dep_a"])
        self._queue.refresh()
        self._queue.mark_completed("dep_a")
        self._queue.refresh()
        assert len(self._queue.ready) == 1
        assert self._queue.ready[0].activity_id == "dep_b"


class TestSchedulerExt:
    """Extended scheduler tests for pause/resume/registry integration."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_sched_ext.db")
        self._store = ActivityStore(db_path=self._db)
        self._mgr = ActivityManager(store=self._store)
        self._resume = ResumeEngine(self._mgr)
        self._results = []

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_pause_resume(self):
        async def run():
            sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
            assert sched.state == "stopped"
            await sched.start()
            assert sched.state == "running"
            await sched.pause()
            assert sched.state == "paused"
            await sched.resume()
            assert sched.state == "running"
            await sched.stop()
            assert sched.state == "stopped"
        asyncio.run(run())

    def test_tick_callback(self):
        async def run():
            sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
            self._mgr.create_activity("Callback test")
            results = []
            sched.on_tick(lambda r: results.append(r))
            await sched.tick()
            assert len(results) == 1
            assert "tick" in results[0]
        asyncio.run(run())

    def test_registry_executor(self):
        sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
        executed = []

        async def mock_executor(**kw):
            executed.append(kw.get("goal", ""))
            return {"ok": True}

        sched.registry.register("goal", mock_executor)
        self._mgr.create_activity("Research topic")
        asyncio.run(sched.tick())
        assert len(executed) == 1
        assert "Research" in executed[0]

    def test_registry_no_executor_fails(self):
        sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
        self._mgr.create_activity("No executor task")
        result = asyncio.run(sched.tick())
        assert result.get("error", "").startswith("no_executor_for_type")

    def test_ticks_increment(self):
        sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
        asyncio.run(sched.tick())
        assert sched.ticks == 1
        asyncio.run(sched.tick())
        assert sched.ticks == 2

    def test_queue_property(self):
        sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
        queue = sched.queue
        assert queue is not None
        assert queue.all == []

    def test_submit_via_scheduler(self):
        sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
        act = sched.queue.submit("sched_sub", goal="Via scheduler")
        assert act is not None
        assert act.activity_id == "sched_sub"

    # ── Worker pool tests ──────────────────────────────────────────────────

    def test_default_max_workers(self):
        sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
        assert sched.max_workers == 3

    def test_max_workers_setter(self):
        sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
        sched.max_workers = 5
        assert sched.max_workers == 5
        with pytest.raises(ValueError):
            sched.max_workers = 0

    def test_running_count_and_activities(self):
        sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
        assert sched.running_count == 0
        assert sched.running_activities == []

    def test_running_count_after_launch(self):
        async def run():
            sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
            sched.max_workers = 2

            async def slow_executor(**kw):
                await asyncio.sleep(10)
                return {"ok": True}

            sched.registry.register("goal", slow_executor)
            self._mgr.create_activity("Task A")
            self._mgr.create_activity("Task B")
            result = await sched.tick()
            assert result["executed"] is True
            assert len(result["launched"]) == 2
            assert sched.running_count == 2
            assert "Task A" in str(sched.running_activities) or len(sched.running_activities) == 2
            await sched.stop()
        asyncio.run(run())

    def test_workers_complete_and_cleanup(self):
        async def run():
            sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
            sched.max_workers = 2

            async def quick_executor(**kw):
                return {"ok": True}

            sched.registry.register("goal", quick_executor)
            act_a = self._mgr.create_activity("Quick A")
            act_b = self._mgr.create_activity("Quick B")
            result = await sched.tick()
            assert len(result["launched"]) == 2
            # Give workers time to finish
            await asyncio.sleep(0.1)
            assert sched.running_count == 0
            assert sched.queue._activities.get(act_a.node_id).status == "completed"
            assert sched.queue._activities.get(act_b.node_id).status == "completed"
            await sched.stop()
        asyncio.run(run())

    def test_get_best_n(self):
        sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)

        async def mock_exec(**kw):
            return {"ok": True}

        sched.registry.register("goal", mock_exec)
        self._mgr.create_activity("A")
        self._mgr.create_activity("B")
        self._mgr.create_activity("C")
        sched.queue.refresh()
        best_2 = sched.queue.get_best_n(2)
        assert len(best_2) == 2
        best_5 = sched.queue.get_best_n(5)
        assert len(best_5) == 3
        best_0 = sched.queue.get_best_n(0)
        assert best_0 == []
        best_with_exclude = sched.queue.get_best_n(2, exclude={best_2[0].activity_id})
        assert best_with_exclude[0].activity_id != best_2[0].activity_id

    def test_worker_pool_respects_max_workers(self):
        async def run():
            sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)
            sched.max_workers = 2

            async def sleeper(**kw):
                await asyncio.sleep(10)
                return {"ok": True}

            sched.registry.register("goal", sleeper)
            self._mgr.create_activity("A")
            self._mgr.create_activity("B")
            self._mgr.create_activity("C")
            result = await sched.tick()
            assert len(result["launched"]) == 2
            # Third should not be launched (all workers busy)
            result2 = await sched.tick()
            assert result2.get("reason") == "all_workers_busy" or result2.get("reason") == "all_workers_busy"
            await sched.stop()
        asyncio.run(run())

    def test_stop_cancels_all_workers(self):
        async def run():
            sched = Scheduler(self._mgr, self._resume, store_db_path=self._db)

            async def slow_executor(**kw):
                await asyncio.sleep(30)
                return {"ok": True}

            sched.registry.register("goal", slow_executor)
            self._mgr.create_activity("A")
            await sched.tick()
            assert sched.running_count == 1
            await sched.stop()
            assert sched.running_count == 0
            assert sched.state == "stopped"
        asyncio.run(run())
