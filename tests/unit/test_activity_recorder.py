"""ActivityRecorder unit tests — planner-side activity recording."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, PropertyMock

from core.activity.manager import ActivityManager
from core.activity.models import ActivityStatus
from core.activity.recorder import ActivityRecorder
from core.activity.storage import ActivityStore
from core.planner.models import SubGoal


class TestActivityRecorder(unittest.TestCase):
    """Unit tests for ActivityRecorder."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_recorder.db")
        self.store = ActivityStore(db_path=self._db)
        self.mgr = ActivityManager(store=self.store)
        self.recorder = ActivityRecorder(self.mgr)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_plan(self, *leaf_descriptions: str) -> SubGoal:
        """Build a SubGoal tree with one leaf per description."""
        root = SubGoal(id="root", description="root", template_id="research_build_email")
        for i, desc in enumerate(leaf_descriptions):
            leaf = SubGoal(
                id=f"leaf_{i}",
                description=desc,
                step_name="build" if "build" in desc.lower() else "research",
            )
            root.children.append(leaf)
        return root

    # ── Goal recording ──────────────────────────────────────────────────────

    def test_01_record_goal(self):
        node = self.recorder.record_goal("Build coffee shop app",
                                          template_id="android_app_build")
        self.assertIsNotNone(node)
        self.assertEqual(node.node_type, "goal")
        self.assertEqual(node.depth, 0)
        self.assertEqual(self.recorder.activity_id, node.node_id)
        self.assertEqual(self.recorder.activity.node_id, node.node_id)

    def test_02_record_goal_no_template(self):
        node = self.recorder.record_goal("Simple task")
        self.assertIsNotNone(node)
        self.assertEqual(node.metadata, {})

    # ── Subgoal recording ──────────────────────────────────────────────────

    def test_03_record_subgoals(self):
        self.recorder.record_goal("Build app")
        plan = self._make_plan("Research competitors", "Build the APK",
                                "Email results")
        self.recorder.record_subgoals(plan)
        tree = self.recorder.get_activity_tree()
        # root + 3 subgoals
        self.assertEqual(len(tree), 4)
        subgoal_nodes = [n for n in tree if n.node_type == "subgoal"]
        self.assertEqual(len(subgoal_nodes), 3)

    def test_04_record_subgoals_no_activity(self):
        # Without recording a goal first, no crash
        plan = self._make_plan("Research")
        self.recorder.record_subgoals(plan)
        # No activity yet, but no crash
        self.assertIsNone(self.recorder.activity_id)

    # ── Agent task recording ────────────────────────────────────────────────

    def test_05_record_agent_tasks(self):
        self.recorder.record_goal("Build app")
        tasks = [
            {"agent_id": "research_agent", "goal": "Research competitors",
             "step": "research", "parameters": {}},
            {"agent_id": "build_agent", "goal": "Build APK",
             "step": "build", "parameters": {"feature": "auth"}},
        ]
        self.recorder.record_agent_tasks(tasks)
        tree = self.recorder.get_activity_tree()
        agent_nodes = [n for n in tree if n.node_type == "agent_call"]
        self.assertEqual(len(agent_nodes), 2)
        self.assertEqual(agent_nodes[0].agent_id, "research_agent")
        self.assertEqual(agent_nodes[1].agent_id, "build_agent")

    def test_06_record_agent_tasks_no_activity(self):
        tasks = [{"agent_id": "a", "goal": "Task", "step": "build"}]
        self.recorder.record_agent_tasks(tasks)  # No crash

    # ── Task result recording ──────────────────────────────────────────────

    def test_07_record_task_success(self):
        self.recorder.record_goal("Build")
        task = {"agent_id": "builder", "goal": "Build APK", "step": "build"}
        self.recorder.record_agent_tasks([task])
        self.recorder.record_task_result(task, success=True,
                                          output={"artifacts": {"apk": "art_001"}})
        tree = self.recorder.get_activity_tree()
        agent_node = [n for n in tree if n.node_type == "agent_call"][0]
        self.assertEqual(agent_node.status, ActivityStatus.COMPLETED)
        self.assertEqual(agent_node.artifacts.get("apk"), "art_001")

    def test_08_record_task_failure(self):
        self.recorder.record_goal("Build")
        task = {"agent_id": "builder", "goal": "Build APK", "step": "build"}
        self.recorder.record_agent_tasks([task])
        self.recorder.record_task_result(task, success=False, error="Compile error")
        tree = self.recorder.get_activity_tree()
        agent_node = [n for n in tree if n.node_type == "agent_call"][0]
        self.assertEqual(agent_node.status, ActivityStatus.FAILED)

    def test_09_record_task_artifacts(self):
        self.recorder.record_goal("Build")
        task = {"agent_id": "b", "goal": "Build", "step": "build"}
        self.recorder.record_agent_tasks([task])
        self.recorder.record_task_artifacts(task, {"apk": "art_001", "log": "art_002"})
        tree = self.recorder.get_activity_tree()
        agent_node = [n for n in tree if n.node_type == "agent_call"][0]
        self.assertEqual(agent_node.status, ActivityStatus.COMPLETED)
        self.assertEqual(agent_node.artifacts.get("apk"), "art_001")
        self.assertEqual(agent_node.artifacts.get("log"), "art_002")

    # ── Completion and failure ────────────────────────────────────────────

    def test_10_record_completion(self):
        self.recorder.record_goal("Build app")
        self.recorder.record_completion({"state": "COMPLETE", "verification": "all passed"})
        act = self.mgr.get_activity(self.recorder.activity_id)
        self.assertEqual(act.status, ActivityStatus.COMPLETED)

    def test_11_record_failure(self):
        self.recorder.record_goal("Failing app")
        self.recorder.record_failure("Build failed")
        act = self.mgr.get_activity(self.recorder.activity_id)
        self.assertEqual(act.status, ActivityStatus.FAILED)
        self.assertIn("Build failed", act.output.get("error", ""))

    # ── Artifact recording ────────────────────────────────────────────────

    def test_12_record_artifact(self):
        self.recorder.record_goal("Build")
        task = {"agent_id": "b", "goal": "Build", "step": "build"}
        self.recorder.record_agent_tasks([task])
        self.recorder.record_artifact(task, "APK output", "art_abc123")
        tree = self.recorder.get_activity_tree()
        art_nodes = [n for n in tree if n.node_type == "artifact"]
        self.assertEqual(len(art_nodes), 1)
        self.assertEqual(art_nodes[0].artifacts.get("APK output"), "art_abc123")

    def test_13_record_artifact_no_task(self):
        self.recorder.record_goal("Build")
        # No agent tasks recorded — artifact goes on root
        self.recorder.record_artifact({"agent_id": "x", "goal": "y", "step": "z"},
                                       "output", "art_xyz")
        tree = self.recorder.get_activity_tree()
        art_nodes = [n for n in tree if n.node_type == "artifact"]
        self.assertEqual(len(art_nodes), 1)

    # ── Workflow linking ──────────────────────────────────────────────────

    def test_14_link_workflow(self):
        self.recorder.record_goal("Build")
        plan = self._make_plan("Research")
        self.recorder.record_subgoals(plan)
        self.recorder.link_workflow("wf_test_123")
        tree = self.recorder.get_activity_tree()
        for node in tree:
            self.assertEqual(node.workflow_id, "wf_test_123")

    # ── Timeline queries ──────────────────────────────────────────────────

    def test_15_get_timeline(self):
        self.recorder.record_goal("Build")
        tasks = [{"agent_id": "a", "goal": "Research", "step": "research"}]
        self.recorder.record_agent_tasks(tasks)
        timeline = self.recorder.get_activity_timeline()
        self.assertGreaterEqual(len(timeline), 2)

    def test_16_get_activity_tree_no_activity(self):
        # Create a fresh recorder with no activity recorded
        r2 = ActivityRecorder(self.mgr)
        self.assertEqual(r2.get_activity_tree(), [])
        self.assertIsNone(r2.activity_id)
        self.assertIsNone(r2.activity)
