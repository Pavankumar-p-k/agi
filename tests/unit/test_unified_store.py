"""Tests for core.planner.unified_store — UnifiedStore."""

import json
import os
import tempfile
import unittest

from core.planner.unified_store import UnifiedStore
from core.planner.protocol import Plan, PlanStatus


class TestUnifiedStore(unittest.TestCase):
    def setUp(self):
        self._tmp_fd, self._tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(self._tmp_fd)
        self.store = UnifiedStore(db_path=self._tmp_path)

    def tearDown(self):
        try:
            os.unlink(self._tmp_path)
        except OSError:
            pass

    def test_create(self):
        plan = self.store.create("test goal")
        self.assertIsNotNone(plan)
        self.assertEqual(plan.goal, "test goal")
        self.assertEqual(plan.status, PlanStatus.DRAFT)
        self.assertEqual(plan.priority, 0)
        self.assertTrue(plan.id.startswith("plan_"))

    def test_create_with_all_fields(self):
        plan = self.store.create(
            "test goal", priority=5, parent_plan_id="parent1",
            blockers=["b1"], next_action="next step",
            tags=["urgent"], deadline="2026-12-31",
        )
        self.assertEqual(plan.priority, 5)
        self.assertEqual(plan.parent_plan_id, "parent1")
        self.assertEqual(plan.blockers, ["b1"])
        self.assertEqual(plan.next_action, "next step")
        self.assertEqual(plan.tags, ["urgent"])
        self.assertEqual(plan.deadline, "2026-12-31")

    def test_get(self):
        created = self.store.create("test goal")
        fetched = self.store.get(created.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, created.id)
        self.assertEqual(fetched.goal, "test goal")

    def test_get_nonexistent(self):
        self.assertIsNone(self.store.get("nonexistent"))

    def test_update(self):
        plan = self.store.create("test goal")
        updated = self.store.update(plan.id, priority=10, status=PlanStatus.ACTIVE)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.priority, 10)
        self.assertEqual(updated.status, PlanStatus.ACTIVE)

    def test_update_partial(self):
        plan = self.store.create("test goal")
        updated = self.store.update(plan.id, goal="updated goal")
        self.assertEqual(updated.goal, "updated goal")
        self.assertEqual(updated.status, PlanStatus.DRAFT)

    def test_delete(self):
        plan = self.store.create("test goal")
        self.assertTrue(self.store.delete(plan.id))
        self.assertIsNone(self.store.get(plan.id))

    def test_delete_nonexistent(self):
        self.assertFalse(self.store.delete("nonexistent"))

    def test_list_all(self):
        self.store.create("goal a", priority=1)
        self.store.create("goal b", priority=2)
        plans = self.store.list_all()
        self.assertEqual(len(plans), 2)

    def test_list_by_status(self):
        p1 = self.store.create("goal a")
        self.store.update(p1.id, status=PlanStatus.ACTIVE)
        self.store.create("goal b")
        active = self.store.list_all(status="active")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].id, p1.id)

    def test_count(self):
        p1 = self.store.create("goal a")
        self.store.update(p1.id, status=PlanStatus.ACTIVE)
        p2 = self.store.create("goal b")
        self.store.update(p2.id, status=PlanStatus.COMPLETED)
        stats = self.store.count()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["active"], 1)
        self.assertEqual(stats["completed"], 1)

    def test_get_highest_priority(self):
        self.store.create("low", priority=1)
        high = self.store.create("high", priority=10)
        self.store.update(high.id, status=PlanStatus.ACTIVE)
        top = self.store.get_highest_priority()
        self.assertEqual(top.id, high.id)

    def test_complete(self):
        plan = self.store.create("test goal")
        completed = self.store.complete(plan.id, result="done")
        self.assertEqual(completed.status, PlanStatus.COMPLETED)
        self.assertEqual(completed.progress, 1.0)
        self.assertEqual(completed.result, "done")

    def test_fail(self):
        plan = self.store.create("test goal")
        failed = self.store.fail(plan.id, reason="error")
        self.assertEqual(failed.status, PlanStatus.FAILED)
        self.assertEqual(failed.result, "error")

    def test_set_progress(self):
        plan = self.store.create("test goal")
        updated = self.store.set_progress(plan.id, 0.75)
        self.assertEqual(updated.progress, 0.75)

    def test_set_progress_clamped(self):
        plan = self.store.create("test goal")
        updated = self.store.set_progress(plan.id, 1.5)
        self.assertEqual(updated.progress, 1.0)

    def test_get_plan_tree(self):
        parent = self.store.create("parent", priority=5)
        self.store.update(parent.id, status=PlanStatus.ACTIVE)
        child = self.store.create("child", priority=1, parent_plan_id=parent.id)
        self.store.update(child.id, status=PlanStatus.ACTIVE)
        tree = self.store.get_plan_tree()
        self.assertGreaterEqual(len(tree), 1)
        root_names = [t["goal"] for t in tree]
        self.assertIn("parent", root_names)


class TestMigration(unittest.TestCase):
    def test_planstore_migration_empty(self):
        store = UnifiedStore()
        count = store.migrate_from_planstore()
        self.assertGreaterEqual(count, 0)

    def test_goalmanager_migration_no_db(self):
        store = UnifiedStore()
        count = store.migrate_from_goalmanager("/nonexistent/test.db")
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
