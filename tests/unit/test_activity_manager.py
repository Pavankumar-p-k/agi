from datetime import datetime
import os
import shutil
import tempfile
import unittest

from core.activity.manager import ActivityManager
from core.activity.models import ActivityStatus
from core.activity.storage import ActivityStore


class TestActivityManager(unittest.TestCase):
    """Unit tests for ActivityManager high-level API."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_activity.db")
        self.store = ActivityStore(db_path=self._db)
        self.mgr = ActivityManager(store=self.store)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ── Activity lifecycle ──────────────────────────────────────────────────

    def test_01_create_activity(self):
        act = self.mgr.create_activity("Build coffee shop app")
        self.assertEqual(act.node_type, "goal")
        self.assertEqual(act.depth, 0)
        self.assertEqual(act.status, ActivityStatus.RUNNING)
        self.assertEqual(act.label, "Build coffee shop app")
        self.assertEqual(act.activity_id, act.node_id)

        fetched = self.mgr.get_activity(act.activity_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.label, "Build coffee shop app")

    def test_02_suspend_and_complete_activity(self):
        act = self.mgr.create_activity("Research task")
        sub = self.mgr.create_subgoal(act, "Phase 1")
        self.mgr.mark_running(sub.node_id)

        self.mgr.suspend_activity(act.activity_id)
        root = self.mgr.get_activity(act.activity_id)
        self.assertEqual(root.status, ActivityStatus.SUSPENDED)

        self.mgr.complete_activity(act.activity_id, output={"summary": "done"})
        root = self.mgr.get_activity(act.activity_id)
        self.assertEqual(root.status, ActivityStatus.COMPLETED)
        self.assertEqual(root.output, {"summary": "done"})

    def test_03_fail_activity(self):
        act = self.mgr.create_activity("Failing task")
        self.mgr.fail_activity(act.activity_id, "Network error")
        root = self.mgr.get_activity(act.activity_id)
        self.assertEqual(root.status, ActivityStatus.FAILED)
        self.assertIn("Network error", root.output.get("error", ""))

    def test_04_suspend_marks_children_suspended(self):
        act = self.mgr.create_activity("Parent")
        sub = self.mgr.create_subgoal(act, "Child")
        self.mgr.mark_running(sub.node_id)
        self.mgr.suspend_activity(act.activity_id)
        sub_fetched = self.mgr.get_activity(sub.node_id)
        self.assertEqual(sub_fetched.status, ActivityStatus.SUSPENDED)

    # ── Sub-goals and tasks ────────────────────────────────────────────────

    def test_05_create_subgoal(self):
        act = self.mgr.create_activity("Build app")
        sub = self.mgr.create_subgoal(act, "Design UI", step_name="design")
        self.assertEqual(sub.node_type, "subgoal")
        self.assertEqual(sub.depth, 1)
        self.assertEqual(sub.parent_id, act.node_id)
        self.assertEqual(sub.status, ActivityStatus.PENDING)
        self.assertEqual(sub.input.get("step_name"), "design")

    def test_06_create_agent_task(self):
        act = self.mgr.create_activity("Deploy")
        task = self.mgr.create_agent_task(act, "builder", "Build the APK",
                                            step_name="build")
        self.assertEqual(task.node_type, "agent_call")
        self.assertEqual(task.depth, 1)
        self.assertEqual(task.agent_id, "builder")
        self.assertEqual(task.status, ActivityStatus.PENDING)

    def test_07_create_agent_task_with_origin(self):
        act = self.mgr.create_activity("Multi-step")
        first = self.mgr.create_agent_task(act, "agent_a", "Step 1")
        second = self.mgr.create_agent_task(act, "agent_b", "Step 2",
                                              parent=act, origin_node_id=first.node_id)
        self.assertEqual(second.origin_node_id, first.node_id)

    def test_08_create_tool_call(self):
        act = self.mgr.create_activity("Tool demo")
        task = self.mgr.create_agent_task(act, "browser", "Navigate")
        tc = self.mgr.create_tool_call(task, "browser_navigate",
                                         input_data={"url": "https://example.com"})
        self.assertEqual(tc.node_type, "tool_call")
        self.assertEqual(tc.depth, 2)
        self.assertEqual(tc.agent_id, "browser")
        self.assertEqual(tc.input.get("url"), "https://example.com")
        self.assertEqual(tc.status, ActivityStatus.PENDING)

    def test_09_create_artifact_node(self):
        act = self.mgr.create_activity("Artifact demo")
        task = self.mgr.create_agent_task(act, "builder", "Build")
        art = self.mgr.create_artifact_node(task, "APK output", "art_abc123")
        self.assertEqual(art.node_type, "artifact")
        self.assertEqual(art.status, ActivityStatus.COMPLETED)
        self.assertEqual(art.artifacts.get("APK output"), "art_abc123")
        self.assertIsNotNone(art.completed_at)

    # ── Status transitions ──────────────────────────────────────────────────

    def test_10_mark_running(self):
        act = self.mgr.create_activity("Running test")
        self.mgr.mark_running(act.node_id)
        fetched = self.mgr.get_activity(act.node_id)
        self.assertEqual(fetched.status, ActivityStatus.RUNNING)

    def test_11_mark_completed(self):
        act = self.mgr.create_activity("Completion test")
        sub = self.mgr.create_subgoal(act, "Sub-task")
        self.mgr.mark_completed(sub.node_id, output={"result": "ok"},
                                 artifacts={"report": "art_xyz"})
        fetched = self.mgr.get_activity(sub.node_id)
        self.assertEqual(fetched.status, ActivityStatus.COMPLETED)
        self.assertEqual(fetched.output, {"result": "ok"})
        self.assertEqual(fetched.artifacts.get("report"), "art_xyz")
        self.assertIsNotNone(fetched.completed_at)

    def test_12_mark_failed(self):
        act = self.mgr.create_activity("Failure test")
        sub = self.mgr.create_subgoal(act, "Failing sub")
        self.mgr.mark_failed(sub.node_id, "Timeout")
        fetched = self.mgr.get_activity(sub.node_id)
        self.assertEqual(fetched.status, ActivityStatus.FAILED)
        self.assertIn("Timeout", fetched.output.get("error", ""))

    # ── Dependencies ────────────────────────────────────────────────────────

    def test_13_add_dependency_and_produces(self):
        act = self.mgr.create_activity("Deps")
        first = self.mgr.create_agent_task(act, "a", "First")
        second = self.mgr.create_agent_task(act, "b", "Second")
        dep = self.mgr.add_dependency(second.node_id, first.node_id)
        self.assertEqual(dep.from_node_id, second.node_id)
        self.assertEqual(dep.to_node_id, first.node_id)
        self.assertEqual(dep.edge_type, "depends_on")

        art = self.mgr.create_artifact_node(first, "Output", "art_out")
        prod = self.mgr.add_produces(first.node_id, art.node_id)
        self.assertEqual(prod.edge_type, "produces")

    def test_14_link_workflow(self):
        act = self.mgr.create_activity("Workflow link")
        self.mgr.link_workflow(act.node_id, "wf_123")
        fetched = self.mgr.get_activity(act.node_id)
        self.assertEqual(fetched.workflow_id, "wf_123")

    # ── Queries ─────────────────────────────────────────────────────────────

    def test_15_get_tree_and_timeline(self):
        act = self.mgr.create_activity("Query test")
        sub = self.mgr.create_subgoal(act, "Sub 1")
        task = self.mgr.create_agent_task(act, "agent", "Task A", parent=sub)
        tree = self.mgr.get_tree(act.activity_id)
        self.assertEqual(len(tree), 3)
        timeline = self.mgr.get_timeline(act.activity_id)
        self.assertEqual(len(timeline), 3)

    def test_16_get_active_activities(self):
        a1 = self.mgr.create_activity("Active 1")
        a2 = self.mgr.create_activity("Active 2")
        self.mgr.complete_activity(a1.activity_id)
        active = self.mgr.get_active_activities()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].node_id, a2.node_id)

    def test_17_resume_candidates(self):
        act = self.mgr.create_activity("Resume test")
        sub = self.mgr.create_subgoal(act, "Sub A")
        task = self.mgr.create_agent_task(act, "agent", "Task B", parent=sub)
        # Only leaf nodes that are PENDING or RUNNING
        candidates = self.mgr.resume_candidates(act.activity_id)
        # sub has PENDING child (task), so sub is excluded; task has no children -> 1
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].node_id, task.node_id)

    def test_18_resume_candidates_excludes_completed(self):
        act = self.mgr.create_activity("Resume exclusion")
        sub = self.mgr.create_subgoal(act, "Sub A")
        task = self.mgr.create_agent_task(act, "agent", "Task B", parent=sub)
        self.mgr.mark_completed(task.node_id)
        candidates = self.mgr.resume_candidates(act.activity_id)
        # task is COMPLETED; sub has no PENDING children -> sub becomes the leaf
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].node_id, sub.node_id)

    # ── Summarize ───────────────────────────────────────────────────────────

    def test_19_summarize(self):
        act = self.mgr.create_activity("Summary test")
        sub = self.mgr.create_subgoal(act, "Sub A")
        self.mgr.create_agent_task(act, "agent_1", "Task 1", parent=sub)
        self.mgr.create_agent_task(act, "agent_2", "Task 2", parent=sub)
        summary = self.mgr.summarize(act.activity_id)
        self.assertEqual(summary["goal"], "Summary test")
        self.assertEqual(summary["total_nodes"], 4)
        self.assertIn("PENDING", summary["by_status"])
        self.assertIn("RUNNING", summary["by_status"])
        self.assertIn("agents_used", summary)
        self.assertEqual(sorted(summary["agents_used"]), ["agent_1", "agent_2"])
        self.assertEqual(summary["depth"], 2)

    def test_20_summarize_not_found(self):
        summary = self.mgr.summarize("nonexistent")
        self.assertIn("error", summary)

    # ── Edge cases ──────────────────────────────────────────────────────────

    def test_21_mark_nonexistent_node(self):
        self.mgr.mark_completed("no_such_node")
        self.mgr.mark_failed("no_such_node", "error")
        self.mgr.mark_running("no_such_node")
        # No crash = success

    def test_22_artifacts_accumulate(self):
        act = self.mgr.create_activity("Artifact accumulate")
        task = self.mgr.create_agent_task(act, "builder", "Build")
        self.mgr.mark_completed(task.node_id, artifacts={"apk": "art_001"})
        fetched = self.mgr.get_activity(task.node_id)
        self.assertEqual(fetched.artifacts.get("apk"), "art_001")
        # Second mark adds to artifacts dict
        self.mgr.mark_completed(task.node_id, artifacts={"log": "art_002"})
        fetched = self.mgr.get_activity(task.node_id)
        self.assertEqual(fetched.artifacts.get("apk"), "art_001")
        self.assertEqual(fetched.artifacts.get("log"), "art_002")

    def test_23_create_subgoal_nested(self):
        act = self.mgr.create_activity("Nested")
        l1 = self.mgr.create_subgoal(act, "Level 1")
        l2 = self.mgr.create_subgoal(l1, "Level 2")
        l3 = self.mgr.create_subgoal(l2, "Level 3")
        self.assertEqual(l1.depth, 1)
        self.assertEqual(l2.depth, 2)
        self.assertEqual(l3.depth, 3)
        tree = self.mgr.get_tree(act.activity_id)
        self.assertEqual(len(tree), 4)
        self.assertEqual([n.node_type for n in tree], ["goal", "subgoal", "subgoal", "subgoal"])
