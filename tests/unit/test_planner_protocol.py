"""Tests for core.planner.protocol — Plan, PlanStatus, Planner protocol."""

import unittest
from core.planner.protocol import Plan, PlanStatus, Planner


class TestPlanStatus(unittest.TestCase):
    def test_values(self):
        self.assertEqual(PlanStatus.DRAFT.value, "draft")
        self.assertEqual(PlanStatus.ACTIVE.value, "active")
        self.assertEqual(PlanStatus.PAUSED.value, "paused")
        self.assertEqual(PlanStatus.IN_PROGRESS.value, "in_progress")
        self.assertEqual(PlanStatus.COMPLETED.value, "completed")
        self.assertEqual(PlanStatus.FAILED.value, "failed")
        self.assertEqual(PlanStatus.CANCELLED.value, "cancelled")
        self.assertEqual(PlanStatus.BLOCKED.value, "blocked")


class TestPlan(unittest.TestCase):
    def test_minimal_plan(self):
        p = Plan(id="p1", goal="test goal")
        self.assertEqual(p.id, "p1")
        self.assertEqual(p.goal, "test goal")
        self.assertEqual(p.status, PlanStatus.DRAFT)
        self.assertEqual(p.priority, 0)

    def test_to_dict(self):
        p = Plan(id="p1", goal="test", status=PlanStatus.ACTIVE, priority=5,
                 tags=["urgent"])
        d = p.to_dict()
        self.assertEqual(d["id"], "p1")
        self.assertEqual(d["goal"], "test")
        self.assertEqual(d["status"], "active")
        self.assertEqual(d["priority"], 5)
        self.assertEqual(d["tags"], ["urgent"])

    def test_from_dict(self):
        d = {
            "id": "p1",
            "goal": "test goal",
            "status": "active",
            "priority": 3,
            "progress": 0.5,
            "blockers": ["blocker1"],
            "deadline": "2026-12-31",
        }
        p = Plan.from_dict(d)
        self.assertEqual(p.id, "p1")
        self.assertEqual(p.goal, "test goal")
        self.assertEqual(p.status, PlanStatus.ACTIVE)
        self.assertEqual(p.priority, 3)
        self.assertEqual(p.progress, 0.5)
        self.assertEqual(p.blockers, ["blocker1"])
        self.assertEqual(p.deadline, "2026-12-31")

    def test_from_goal_dict(self):
        d = {
            "objective": "goal objective",
            "status": "active",
            "priority": 2,
            "progress": 0.3,
            "parent_goal_id": "parent1",
            "blockers": '["b1"]',
            "deadline": "2026-12-31",
        }
        p = Plan.from_goal_dict(d)
        self.assertEqual(p.goal, "goal objective")
        self.assertEqual(p.status, PlanStatus.ACTIVE)
        self.assertEqual(p.parent_plan_id, "parent1")

    def test_roundtrip(self):
        p1 = Plan(id="p1", goal="test", status=PlanStatus.IN_PROGRESS,
                  priority=1, tags=["a", "b"])
        p2 = Plan.from_dict(p1.to_dict())
        self.assertEqual(p1.id, p2.id)
        self.assertEqual(p1.goal, p2.goal)
        self.assertEqual(p1.status, p2.status)
        self.assertEqual(p1.priority, p2.priority)
        self.assertEqual(p1.tags, p2.tags)

    def test_from_dict_fallback_objective(self):
        p = Plan.from_dict({"id": "p1", "objective": "obj"})
        self.assertEqual(p.goal, "obj")


class TestPlannerProtocol(unittest.TestCase):
    def test_is_protocol(self):
        import typing
        self.assertTrue(hasattr(Planner, "_is_protocol"))


if __name__ == "__main__":
    unittest.main()
