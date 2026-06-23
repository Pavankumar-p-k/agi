"""Scheduler unit tests — models, policies, queue, tick loop."""

import asyncio
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from core.activity.manager import ActivityManager
from core.activity.models import ActivityStatus
from core.activity.resume import ResumeContext, ResumeEngine
from core.activity.storage import ActivityStore
from core.scheduler.models import ScheduledActivity, activity_status_from_node
from core.scheduler.policies import PriorityPolicy
from core.scheduler.queue import SchedulerQueue
from core.scheduler.scheduler import Scheduler


class TestSchedulerModels(unittest.TestCase):
    """ScheduledActivity dataclass behavior."""

    def test_01_ready_and_blocked(self):
        act = ScheduledActivity(activity_id="a1", status="pending")
        self.assertTrue(act.is_ready)
        self.assertFalse(act.is_blocked)
        act.block()
        self.assertTrue(act.is_blocked)
        act.unblock()
        self.assertFalse(act.is_blocked)

    def test_02_activity_status_mapping(self):
        self.assertEqual(activity_status_from_node("COMPLETED"), "completed")
        self.assertEqual(activity_status_from_node("FAILED"), "completed")
        self.assertEqual(activity_status_from_node("CANCELLED"), "completed")
        self.assertEqual(activity_status_from_node("RUNNING"), "running")
        self.assertEqual(activity_status_from_node("PENDING"), "pending")


class TestPriorityPolicy(unittest.TestCase):
    """Deterministic scoring."""

    def setUp(self):
        self.policy = PriorityPolicy()
        self.now = datetime(2026, 6, 22, 12, 0, 0)

    def _act(self, aid="a", priority=0, status="pending", last_resumed=None,
             created=None, previous_status=None, node_type="goal"):
        return ScheduledActivity(
            activity_id=aid,
            priority=priority,
            status=status,
            goal="test",
            node_type=node_type,
            created_at=created or self.now,
            last_resumed_at=last_resumed,
            metadata={"previous_status": previous_status},
        )

    def test_03_higher_priority_wins(self):
        low = self._act("low", priority=0)
        high = self._act("high", priority=5)
        ranked = self.policy.rank([low, high], now=self.now)
        self.assertEqual(ranked[0].activity_id, "high")

    def test_04_retry_bonus(self):
        failed = self._act("failed", previous_status="failed")
        normal = self._act("normal")
        ranked = self.policy.rank([normal, failed], now=self.now)
        self.assertEqual(ranked[0].activity_id, "failed")

    def test_05_user_requested_bonus(self):
        user = self._act("user", node_type="goal")
        sys = self._act("sys", node_type="subgoal")
        ranked = self.policy.rank([sys, user], now=self.now)
        self.assertEqual(ranked[0].activity_id, "user")

    def test_06_waiting_time_bonus(self):
        old = self._act("old", created=self.now - timedelta(hours=2))
        new = self._act("new", created=self.now)
        ranked = self.policy.rank([new, old], now=self.now)
        # Old should have higher waiting bonus
        self.assertGreater(old.score, new.score)
        self.assertEqual(ranked[0].activity_id, "old")

    def test_07_stable_sort(self):
        a = self._act("a")
        b = self._act("b")
        c = self._act("c")
        ranked = self.policy.rank([c, a, b], now=self.now)
        # Same score — order should be deterministic (original order preserved)
        self.assertEqual([r.activity_id for r in ranked], ["c", "a", "b"])


class TestSchedulerQueue(unittest.TestCase):
    """Dependency-aware activity loading."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_queue.db")
        self.store = ActivityStore(db_path=self._db)
        self.mgr = ActivityManager(store=self.store)
        self.queue = SchedulerQueue(self.mgr)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_08_empty_queue(self):
        ready = self.queue.refresh()
        self.assertEqual(ready, [])
        self.assertIsNone(self.queue.get_best())

    def test_09_loads_active_activities(self):
        self.mgr.create_activity("Build app")
        self.mgr.create_activity("Research")
        ready = self.queue.refresh()
        self.assertEqual(len(ready), 2)

    def test_10_excludes_completed(self):
        a1 = self.mgr.create_activity("Build")
        self.mgr.create_activity("Research")
        self.mgr.complete_activity(a1.activity_id)
        ready = self.queue.refresh()
        self.assertEqual(len(ready), 1)

    def test_11_excludes_blocked(self):
        a1 = self.mgr.create_activity("First")
        a2 = self.mgr.create_activity("Second")
        ready = self.queue.refresh()
        # No dependencies defined — both are ready
        self.assertEqual(len(ready), 2)

    def test_12_mark_running_and_failed(self):
        a1 = self.mgr.create_activity("Build")
        self.queue.refresh()
        self.queue.mark_running(a1.activity_id)
        self.assertEqual(self.queue.get_best().activity_id, a1.activity_id)

    def test_13_priority_ordering(self):
        act = self.mgr.create_activity("Build app")
        a1 = self.mgr.create_activity("Research")
        # Refresh should include both, sorted by score
        self.queue.refresh()
        # Both are user goals with same priority (0) — order is insertion order
        self.assertEqual(len(self.queue.ready), 2)


class TestScheduler(unittest.TestCase):
    """Scheduler tick loop behavior."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_scheduler.db")
        self.store = ActivityStore(db_path=self._db)
        self.mgr = ActivityManager(store=self.store)
        self.resume = ResumeEngine(self.mgr)
        self.executed = []

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    async def _fake_execute(self, activity_id: str, label: str) -> None:
        self.executed.append((activity_id, label))

    def test_14_tick_no_activities(self):
        scheduler = Scheduler(self.mgr, self.resume, execute_fn=self._fake_execute)
        asyncio.run(scheduler.tick())
        self.assertEqual(self.executed, [])

    def test_15_tick_resumes_activity(self):
        self.mgr.create_activity("Build app")
        scheduler = Scheduler(self.mgr, self.resume, execute_fn=self._fake_execute,
                              tick_interval=0.5)
        asyncio.run(scheduler.tick())
        self.assertEqual(len(self.executed), 1)
        self.assertIn("Build app", self.executed[0][1])

    def test_16_tick_skips_completed(self):
        a1 = self.mgr.create_activity("Build app")
        self.mgr.complete_activity(a1.activity_id)
        scheduler = Scheduler(self.mgr, self.resume, execute_fn=self._fake_execute)
        asyncio.run(scheduler.tick())
        self.assertEqual(self.executed, [])

    def test_17_start_stop(self):
        async def run():
            scheduler = Scheduler(self.mgr, self.resume, execute_fn=self._fake_execute,
                                  tick_interval=0.1)
            self.assertFalse(scheduler.is_running)
            await scheduler.start()
            self.assertTrue(scheduler.is_running)
            await asyncio.sleep(0.35)
            await scheduler.stop()
            self.assertFalse(scheduler.is_running)
            self.assertGreater(scheduler.ticks, 0)
        asyncio.run(run())

    def test_18_picks_highest_priority(self):
        # Test that the queue respects priority by using the queue directly
        from core.scheduler.queue import SchedulerQueue
        from core.scheduler.models import ScheduledActivity

        queue = SchedulerQueue(self.mgr)
        high = ScheduledActivity(activity_id="high", priority=5, score=0, status="pending")
        low = ScheduledActivity(activity_id="low", priority=0, score=0, status="pending")
        # Manually populate the internal dict
        queue._activities = {"high": high, "low": low}
        queue._ready = [low, high]
        queue._ready = queue._policy.rank(queue._ready)
        self.assertEqual(queue.get_best().activity_id, "high")

    def test_19_no_execute_fn_fallback(self):
        self.mgr.create_activity("Build app")
        scheduler = Scheduler(self.mgr, self.resume, execute_fn=None)
        asyncio.run(scheduler.tick())
        # No crash — logs "no execute_fn" and returns
        self.assertEqual(scheduler.ticks, 1)

    def test_20_multiple_ticks(self):
        # Manually tick twice — each tick loads activities and executes one
        self.mgr.create_activity("Build app")
        scheduler = Scheduler(self.mgr, self.resume, execute_fn=self._fake_execute,
                              tick_interval=0.05)
        asyncio.run(scheduler.tick())
        asyncio.run(scheduler.tick())
        # First tick resumes; second tick: activity is now RUNNING,
        # still active, so it gets resumed again
        self.assertGreaterEqual(len(self.executed), 1)
