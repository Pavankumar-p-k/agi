"""ResumeEngine unit tests — resume point finding, context reconstruction."""

import os
import shutil
import tempfile
import unittest

from core.activity.manager import ActivityManager
from core.activity.models import ActivityStatus
from core.activity.resume import ResumeEngine
from core.activity.storage import ActivityStore


class TestResumeEngine(unittest.TestCase):
    """Unit tests for ResumeEngine resume point finding."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_resume.db")
        self.store = ActivityStore(db_path=self._db)
        self.mgr = ActivityManager(store=self.store)
        self.engine = ResumeEngine(self.mgr)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ── Basic resume point finding ──────────────────────────────────────────

    def test_01_resume_from_pending_subgoal(self):
        act = self.mgr.create_activity("Build app")
        sub = self.mgr.create_subgoal(act, "Design UI")
        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.target_node.node_id, sub.node_id)
        self.assertEqual(ctx.target_label, "Design UI")
        self.assertEqual(len(ctx.ancestors), 2)  # root + sub
        self.assertEqual(ctx.ancestors[0].node_id, act.node_id)

    def test_02_resume_from_pending_agent_task(self):
        act = self.mgr.create_activity("Deploy")
        sub = self.mgr.create_subgoal(act, "Build")
        task = self.mgr.create_agent_task(act, "builder", "Build APK", parent=sub)
        ctx = self.engine.find_resume_point(act.activity_id)
        # task is deepest incomplete leaf
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.target_node.node_id, task.node_id)
        self.assertEqual(ctx.ancestors[0].node_id, act.node_id)
        self.assertEqual(ctx.ancestors[1].node_id, sub.node_id)
        self.assertEqual(ctx.ancestors[2].node_id, task.node_id)

    def test_03_resume_after_child_completed(self):
        act = self.mgr.create_activity("Build")
        sub = self.mgr.create_subgoal(act, "Build")
        task = self.mgr.create_agent_task(act, "builder", "Build APK", parent=sub)
        self.mgr.mark_completed(task.node_id)
        # sub is now the resume point (all children completed, but sub is still PENDING)
        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.target_node.node_id, sub.node_id)

    def test_04_resume_shallowest_first(self):
        act = self.mgr.create_activity("Multi-step")
        s1 = self.mgr.create_subgoal(act, "Research")
        s2 = self.mgr.create_subgoal(act, "Build")
        task_a = self.mgr.create_agent_task(act, "a", "Task A", parent=s1)
        task_b = self.mgr.create_agent_task(act, "b", "Task B", parent=s2)
        # After completing task_a, s1 is also a candidate
        self.mgr.mark_completed(task_a.node_id)
        # Candidates: s1 (depth 1, all children done), task_b (depth 2)
        # Shallowest first = s1
        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.target_node.node_id, s1.node_id)

    # ── Accumulated artifacts and input ────────────────────────────────────

    def test_05_accumulated_artifacts(self):
        act = self.mgr.create_activity("Build app")
        research = self.mgr.create_subgoal(act, "Research")
        research_task = self.mgr.create_agent_task(act, "researcher",
                                                     "Research competitors",
                                                     parent=research)
        self.mgr.mark_completed(research_task.node_id,
                                 artifacts={"report": "art_001"})

        build = self.mgr.create_subgoal(act, "Build")
        build_task = self.mgr.create_agent_task(act, "builder",
                                                  "Build APK", parent=build)

        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertIsNotNone(ctx)
        # build_task is the candidate (only after research_task is done)
        # artifacts should include the research report
        self.assertIn("report", ctx.accumulated_artifacts)
        self.assertEqual(ctx.accumulated_artifacts["report"], "art_001")

    def test_06_accumulated_input(self):
        act = self.mgr.create_activity("Research task")
        sub = self.mgr.create_subgoal(act, "Phase 1", step_name="phase1")
        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertEqual(ctx.accumulated_input.get("step_name"), "phase1")

    def test_07_root_goal(self):
        act = self.mgr.create_activity("Build coffee shop app")
        sub = self.mgr.create_subgoal(act, "Design")
        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertEqual(ctx.root_goal, "Build coffee shop app")

    # ── Edge cases ──────────────────────────────────────────────────────────

    def test_08_completed_activity_returns_none(self):
        act = self.mgr.create_activity("Quick task")
        self.mgr.complete_activity(act.activity_id)
        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertIsNone(ctx)

    def test_09_nonexistent_activity_returns_none(self):
        ctx = self.engine.find_resume_point("no_such_activity")
        self.assertIsNone(ctx)

    def test_10_no_incomplete_leaves_but_root_is_running(self):
        act = self.mgr.create_activity("Full tree")
        sub = self.mgr.create_subgoal(act, "Sub")
        task = self.mgr.create_agent_task(act, "agent", "Task", parent=sub)
        self.mgr.mark_completed(task.node_id)
        self.mgr.mark_completed(sub.node_id)
        # All leaves are terminal, but root is still RUNNING -> root is the candidate
        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.target_node.node_id, act.node_id)

    def test_11_suspended_activity_can_resume(self):
        act = self.mgr.create_activity("Paused")
        sub = self.mgr.create_subgoal(act, "Half done")
        self.mgr.suspend_activity(act.activity_id)
        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.target_node.node_id, sub.node_id)

    def test_12_agent_properties(self):
        act = self.mgr.create_activity("Agent resume")
        sub = self.mgr.create_subgoal(act, "Build")
        task = self.mgr.create_agent_task(act, "builder", "Build APK", parent=sub)
        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertTrue(ctx.is_for_agent)
        self.assertEqual(ctx.agent_id, "builder")

    def test_13_not_for_agent(self):
        act = self.mgr.create_activity("Goal resume")
        sub = self.mgr.create_subgoal(act, "Subgoal")
        ctx = self.engine.find_resume_point(act.activity_id)
        self.assertFalse(ctx.is_for_agent)
        self.assertIsNone(ctx.agent_id)

    # ── mark_resumed ────────────────────────────────────────────────────────

    def test_14_mark_resumed(self):
        act = self.mgr.create_activity("Resume mark")
        sub = self.mgr.create_subgoal(act, "Sub")
        ctx = self.engine.find_resume_point(act.activity_id)
        self.engine.mark_resumed(ctx)
        fetched = self.mgr.get_activity(sub.node_id)
        self.assertEqual(fetched.status, ActivityStatus.RUNNING)
        fetched_act = self.mgr.get_activity(act.node_id)
        self.assertEqual(fetched_act.status, ActivityStatus.RUNNING)

    def test_15_mark_resumed_only_pending_or_suspended(self):
        act = self.mgr.create_activity("Selective mark")
        sub = self.mgr.create_subgoal(act, "Sub")
        task = self.mgr.create_agent_task(act, "agent", "Task", parent=sub)
        self.mgr.mark_running(task.node_id)
        # task is already RUNNING, sub is PENDING
        self.engine.mark_resumed(self.engine.find_resume_point(act.activity_id))
        # task stays RUNNING
        self.assertEqual(
            self.mgr.get_activity(task.node_id).status, ActivityStatus.RUNNING)

    # ── resume_all_candidates ──────────────────────────────────────────────

    def test_16_resume_all_candidates(self):
        act = self.mgr.create_activity("Multi-candidate")
        s1 = self.mgr.create_subgoal(act, "Research")
        s2 = self.mgr.create_subgoal(act, "Build")
        ctxs = self.engine.resume_all_candidates(act.activity_id)
        self.assertEqual(len(ctxs), 2)

    def test_17_resume_all_candidates_completed_activity(self):
        act = self.mgr.create_activity("Done")
        self.mgr.complete_activity(act.activity_id)
        ctxs = self.engine.resume_all_candidates(act.activity_id)
        self.assertEqual(len(ctxs), 0)

    def test_18_resume_all_candidates_context_has_artifacts(self):
        act = self.mgr.create_activity("Artifacts chain")
        s1 = self.mgr.create_subgoal(act, "Research")
        t1 = self.mgr.create_agent_task(act, "r", "Research", parent=s1)
        self.mgr.mark_completed(t1.node_id, artifacts={"paper": "art_001"})
        s2 = self.mgr.create_subgoal(act, "Build")
        ctxs = self.engine.resume_all_candidates(act.activity_id)
        for ctx in ctxs:
            if ctx.target_node.node_id == s2.node_id:
                self.assertIn("paper", ctx.accumulated_artifacts)
                break
        else:
            self.fail("Build subgoal not found in candidates")

    # ── activity_summary ────────────────────────────────────────────────────

    def test_19_activity_summary(self):
        act = self.mgr.create_activity("Summary test")
        self.mgr.create_subgoal(act, "Sub A")
        summary = self.engine.activity_summary(act.activity_id)
        self.assertIn("Summary test", summary)
        self.assertIn("Incomplete leaves: 1", summary)
        self.assertIn("Sub A", summary)

    def test_20_activity_summary_not_found(self):
        summary = self.engine.activity_summary("no_such")
        self.assertIn("not found", summary)

    def test_21_activity_summary_completed(self):
        act = self.mgr.create_activity("Done task")
        self.mgr.complete_activity(act.activity_id)
        summary = self.engine.activity_summary(act.activity_id)
        self.assertIn("COMPLETED", summary)
        self.assertIn("Incomplete leaves: 0", summary)
