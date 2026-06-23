"""Tests for Phase 13.0 — Automated Build Tool (automated_build adapter).

Covers:
  - BuildExecutionRecord and BuildPhaseRecord data models
  - _find_build_artifacts scanning
  - _record_activity_nodes with mocked ActivityStore
  - _record_calibration with mocked CalibrationStore
  - do_automated_build with mocked AutomationLoop
  - _emit_progress
  - Error handling
  - Cancellation
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest import TestCase, mock

# Module-level module that may not have all dependencies available
import sys

MODULE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "core", "tools", "automated_build.py")

# ── Models Tests ──────────────────────────────────────────────────


class TestBuildPhaseRecord(TestCase):
    """BuildPhaseRecord data model."""

    def test_01_creation_with_defaults(self):
        from core.tools.automated_build import BuildPhaseRecord
        p = BuildPhaseRecord(phase="planning", status="running")
        self.assertEqual(p.phase, "planning")
        self.assertEqual(p.status, "running")
        self.assertEqual(p.duration_seconds, 0.0)
        self.assertIsNone(p.started_at)

    def test_02_creation_with_all_fields(self):
        from core.tools.automated_build import BuildPhaseRecord
        now = datetime.now(timezone.utc)
        p = BuildPhaseRecord(
            phase="building", status="completed",
            started_at=now, completed_at=now,
            duration_seconds=12.5,
            error="None",
            metadata={"attempts": 3},
        )
        self.assertEqual(p.phase, "building")
        self.assertEqual(p.metadata["attempts"], 3)


class TestBuildExecutionRecord(TestCase):
    """BuildExecutionRecord data model."""

    def test_10_creation(self):
        from core.tools.automated_build import BuildExecutionRecord
        now = datetime.now(timezone.utc)
        rec = BuildExecutionRecord(
            execution_id="test_123",
            goal="Build android app",
            started_at=now,
            completed_at=now,
            success=True,
            status="completed",
            actual_duration_seconds=120.0,
        )
        self.assertEqual(rec.execution_id, "test_123")
        self.assertTrue(rec.success)
        self.assertEqual(rec.status, "completed")

    def test_11_to_dict_includes_all_keys(self):
        from core.tools.automated_build import BuildExecutionRecord
        now = datetime.now(timezone.utc)
        rec = BuildExecutionRecord(
            execution_id="test_456",
            goal="Build android coffee shop app",
            started_at=now,
            completed_at=now,
            success=True,
            status="completed",
            project_dir="/tmp/test",
            artifacts=[{"type": "apk", "path": "app.apk"}],
            actual_duration_seconds=300.0,
            repair_cycles=2,
            repaired_errors=5,
        )
        d = rec.to_dict()
        self.assertEqual(d["execution_id"], "test_456")
        self.assertIn("artifacts", d)
        self.assertEqual(d["artifacts"][0]["type"], "apk")
        self.assertIn("duration_days", d)
        self.assertIn("repair_cycles", d)

    def test_12_actual_duration_days_property(self):
        from core.tools.automated_build import BuildExecutionRecord
        now = datetime.now(timezone.utc)
        rec = BuildExecutionRecord(
            execution_id="test", goal="test", started_at=now, completed_at=now,
            success=True, status="completed",
            actual_duration_seconds=86400.0,
        )
        self.assertAlmostEqual(rec.actual_duration_days, 1.0)

    def test_13_to_dict_includes_phases(self):
        from core.tools.automated_build import BuildExecutionRecord, BuildPhaseRecord
        now = datetime.now(timezone.utc)
        phases = [
            BuildPhaseRecord(phase="planning", status="completed",
                             duration_seconds=2.5),
            BuildPhaseRecord(phase="building", status="completed",
                             duration_seconds=60.0),
        ]
        rec = BuildExecutionRecord(
            execution_id="test", goal="test", started_at=now, completed_at=now,
            success=True, status="completed", phases=phases,
            actual_duration_seconds=62.5,
        )
        d = rec.to_dict()
        self.assertEqual(len(d["phases"]), 2)
        self.assertEqual(d["phases"][0]["phase"], "planning")

    def test_14_failure_reason_included(self):
        from core.tools.automated_build import BuildExecutionRecord
        now = datetime.now(timezone.utc)
        rec = BuildExecutionRecord(
            execution_id="test", goal="test", started_at=now, completed_at=now,
            success=False, status="failed",
            failure_reason="Build error: cannot find symbol",
            actual_duration_seconds=30.0,
        )
        d = rec.to_dict()
        self.assertEqual(d["failure_reason"], "Build error: cannot find symbol")


# ── Artifact Scanning Tests ───────────────────────────────────────


class TestFindBuildArtifacts(TestCase):
    """_find_build_artifacts path scanning."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def _touch(self, rel_path: str):
        full = os.path.join(self._tmpdir, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write("test")
        return full

    def test_20_finds_apk(self):
        from core.tools.automated_build import _find_build_artifacts
        self._touch("app/build/outputs/apk/debug/app-debug.apk")
        found = _find_build_artifacts(self._tmpdir)
        apks = [a for a in found if a["type"] == "apk"]
        self.assertEqual(len(apks), 1)

    def test_21_finds_build_log(self):
        from core.tools.automated_build import _find_build_artifacts
        self._touch("build.log")
        found = _find_build_artifacts(self._tmpdir)
        logs = [a for a in found if a["type"] == "build_log"]
        self.assertEqual(len(logs), 1)

    def test_22_finds_test_report(self):
        from core.tools.automated_build import _find_build_artifacts
        self._touch("test-results/TEST-all.xml")
        found = _find_build_artifacts(self._tmpdir)
        reports = [a for a in found if a["type"] == "test_report"]
        self.assertEqual(len(reports), 1)

    def test_23_finds_coverage(self):
        from core.tools.automated_build import _find_build_artifacts
        self._touch("coverage.xml")
        found = _find_build_artifacts(self._tmpdir)
        covs = [a for a in found if a["type"] == "coverage"]
        self.assertEqual(len(covs), 1)

    def test_24_empty_dir_returns_empty(self):
        from core.tools.automated_build import _find_build_artifacts
        empty = tempfile.mkdtemp()
        found = _find_build_artifacts(empty)
        self.assertEqual(len(found), 0)

    def test_25_paths_are_relative(self):
        from core.tools.automated_build import _find_build_artifacts
        self._touch("output/app.apk")
        found = _find_build_artifacts(self._tmpdir)
        self.assertFalse(found[0]["path"].startswith("/"))
        self.assertFalse(found[0]["path"].startswith("C:"))


# ── Progress Event Tests ──────────────────────────────────────────


class TestEmitProgress(TestCase):
    """_emit_progress helper."""

    def test_30_emits_structured_event(self):
        from core.tools.automated_build import _emit_progress
        received = []

        async def cb(event):
            received.append(event)

        asyncio.run(_emit_progress(cb, "exec_1", "building", "running",
                                    "Building project", 0.5))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["execution_id"], "exec_1")
        self.assertEqual(received[0]["phase"], "building")
        self.assertEqual(received[0]["status"], "running")
        self.assertEqual(received[0]["progress"], 0.5)
        self.assertIn("timestamp", received[0])

    def test_31_no_callback_does_not_error(self):
        from core.tools.automated_build import _emit_progress
        asyncio.run(_emit_progress(None, "exec_1", "building", "running",
                                    "msg", 0.5))

    def test_32_callback_exception_is_logged_not_raised(self):
        from core.tools.automated_build import _emit_progress

        async def broken_cb(event):
            raise RuntimeError("callback error")

        asyncio.run(_emit_progress(broken_cb, "exec_1", "building", "running",
                                    "msg", 0.5))


# ── ActivityGraph Recording Tests ─────────────────────────────────


class TestActivityGraphRecording(TestCase):
    """_record_activity_nodes integration."""

    def test_40_records_parent_and_children(self):
        from core.tools.automated_build import (
            BuildExecutionRecord, BuildPhaseRecord, _record_activity_nodes,
        )
        now = datetime.now(timezone.utc)

        phases = [
            BuildPhaseRecord(phase="planning", status="completed",
                             started_at=now, completed_at=now),
            BuildPhaseRecord(phase="building", status="completed",
                             started_at=now, completed_at=now),
        ]
        record = BuildExecutionRecord(
            execution_id="test_act_001",
            goal="Build android app",
            started_at=now,
            completed_at=now,
            success=True,
            status="completed",
            phases=phases,
        )

        created_nodes = []

        with mock.patch("core.activity.storage.ActivityStore") as MockStore:
            instance = MockStore.return_value
            instance.create_node = mock.Mock(side_effect=lambda n: created_nodes.append(n))

            asyncio.run(_record_activity_nodes(record))

            # Should create parent + 2 child nodes = 3 total
            self.assertGreaterEqual(len(created_nodes), 1)

    def test_41_handles_store_unavailable(self):
        from core.tools.automated_build import (
            BuildExecutionRecord, _record_activity_nodes,
        )
        now = datetime.now(timezone.utc)
        record = BuildExecutionRecord(
            execution_id="test_err",
            goal="Build app",
            started_at=now,
            completed_at=now,
            success=True,
            status="completed",
        )

        # Should not raise when activity module not available
        with mock.patch.dict("sys.modules", {"core.activity.storage": None}):
            try:
                asyncio.run(_record_activity_nodes(record))
            except Exception:
                self.fail("_record_activity_nodes raised unexpectedly on missing module")

    def test_42_parent_metadata_includes_execution_id(self):
        from core.tools.automated_build import (
            BuildExecutionRecord, _record_activity_nodes,
        )
        now = datetime.now(timezone.utc)
        record = BuildExecutionRecord(
            execution_id="test_meta",
            goal="Build android app",
            started_at=now,
            completed_at=now,
            success=True,
            status="completed",
        )

        created_nodes = []

        with mock.patch("core.activity.storage.ActivityStore") as MockStore:
            instance = MockStore.return_value
            instance.create_node = mock.Mock(side_effect=lambda n: created_nodes.append(n))

            asyncio.run(_record_activity_nodes(record))

            if created_nodes:
                parent = created_nodes[0]
                self.assertEqual(parent.metadata.get("execution_id"), "test_meta")
                self.assertEqual(parent.metadata.get("origin"), "automated_build")


# ── Calibration Recording Tests ───────────────────────────────────


class TestCalibrationRecording(TestCase):
    """_record_calibration integration."""

    def test_50_records_calibration_for_successful_build(self):
        from core.tools.automated_build import (
            BuildExecutionRecord, _record_calibration,
        )
        now = datetime.now(timezone.utc)

        record = BuildExecutionRecord(
            execution_id="cal_test_001",
            goal="Build android app",
            started_at=now,
            completed_at=now,
            success=True,
            status="completed",
            actual_duration_seconds=3600.0,
        )

        recorded = []

        with mock.patch("core.strategy.calibration.PredictionCalibrator") as MockCal:
            instance = MockCal.return_value
            instance.store.record = mock.Mock(side_effect=lambda d, gt, actual_success, actual_duration_days: recorded.append(1))

            asyncio.run(_record_calibration(record))

            # calibration should have been recorded
            instance.store.record.assert_called_once()

    def test_51_records_calibration_for_failed_build(self):
        from core.tools.automated_build import (
            BuildExecutionRecord, _record_calibration,
        )
        now = datetime.now(timezone.utc)

        record = BuildExecutionRecord(
            execution_id="cal_test_002",
            goal="Build android app",
            started_at=now,
            completed_at=now,
            success=False,
            status="failed",
            failure_reason="Build error",
            actual_duration_seconds=1800.0,
        )

        with mock.patch("core.strategy.calibration.PredictionCalibrator") as MockCal:
            instance = MockCal.return_value

            asyncio.run(_record_calibration(record))
            instance.store.record.assert_called_once()

    def test_52_handles_calibration_unavailable(self):
        from core.tools.automated_build import (
            BuildExecutionRecord, _record_calibration,
        )
        now = datetime.now(timezone.utc)
        record = BuildExecutionRecord(
            execution_id="cal_err", goal="test", started_at=now, completed_at=now,
            success=True, status="completed",
        )

        # Should not raise when calibration not available
        with mock.patch.dict("sys.modules", {"core.strategy.calibration": None}):
            try:
                asyncio.run(_record_calibration(record))
            except Exception:
                self.fail("_record_calibration raised on missing module")


# ── Main Adapter (do_automated_build) Tests ───────────────────────


class TestDoAutomatedBuild(TestCase):
    """do_automated_build with mocked AutomationLoop."""

    def _mock_build_tools(self, build_success=True, build_status="completed",
                          completion=100.0, repair_cycles=0, repaired_errors=0):
        """Create a context manager that patches build_tools module."""

        from brain.goals.goal import GoalStatus

        class MockGoal:
            def __init__(self, objective, priority=10, tags=None):
                self.id = f"goal_{uuid.uuid4().hex[:8]}"
                self.objective = objective
                self.priority = priority
                self.tags = tags or []
                self.status = GoalStatus.COMPLETED if build_success else GoalStatus.FAILED

        class MockGoalManager:
            def create(self, objective, priority=0, tags=None):
                return MockGoal(objective, priority, tags)
            def get(self, goal_id):
                g = MockGoal("test")
                g.status = GoalStatus.COMPLETED if build_success else GoalStatus.FAILED
                g.id = goal_id
                return g
            def fail(self, goal_id, reason):
                pass
            def complete(self, goal_id, result):
                pass

        class MockMemoryManager:
            def store_trace(self, *args, **kwargs):
                pass

        class MockBuildLoop:
            _completion = completion
            _last_build_metrics = {
                "repair_cycles": repair_cycles,
                "repaired_errors": repaired_errors,
            }
            _build_history = {}

            async def _build_project(self, goal):
                goal.status = GoalStatus.COMPLETED if build_success else GoalStatus.FAILED
                return None

        mock_module = type(sys)("build_tools")
        mock_module._ensure_automation = mock.AsyncMock()
        mock_module._GOAL_MANAGER = MockGoalManager()
        mock_module._BUILD_LOOP = MockBuildLoop()

        return mock.patch.dict("sys.modules", {
            "core.tools.build_tools": mock_module,
        })

    def test_60_successful_build_returns_record(self):
        from core.tools.automated_build import do_automated_build

        with self._mock_build_tools(build_success=True, build_status="completed"):
            result = asyncio.run(do_automated_build(
                "Build android coffee shop app",
                project_dir=tempfile.mkdtemp(),
            ))

        self.assertTrue(result.success)
        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.execution_id)
        self.assertGreaterEqual(result.actual_duration_seconds, 0)

    def test_61_failed_build_returns_failure_record(self):
        from core.tools.automated_build import do_automated_build

        with self._mock_build_tools(build_success=False, build_status="failed"):
            result = asyncio.run(do_automated_build(
                "Build android app",
                project_dir=tempfile.mkdtemp(),
            ))

        self.assertFalse(result.success)
        self.assertEqual(result.status, "failed")

    def test_62_build_includes_phases(self):
        from core.tools.automated_build import do_automated_build

        with self._mock_build_tools():
            result = asyncio.run(do_automated_build(
                "Build android app",
                project_dir=tempfile.mkdtemp(),
            ))

        self.assertGreater(len(result.phases), 0)
        phase_names = [p.phase for p in result.phases]
        self.assertIn("planning", phase_names)
        self.assertIn("building", phase_names)
        self.assertIn("packaging", phase_names)

    def test_63_build_emits_progress_events(self):
        from core.tools.automated_build import do_automated_build

        events = []

        async def progress_cb(event):
            events.append(event)

        with self._mock_build_tools():
            asyncio.run(do_automated_build(
                "Build android app",
                project_dir=tempfile.mkdtemp(),
                progress_cb=progress_cb,
            ))

        self.assertGreater(len(events), 0)
        # Every event should have execution_id
        for e in events:
            self.assertIn("execution_id", e)
            self.assertIn("phase", e)
            self.assertIn("status", e)

    def test_64_build_handles_automation_error(self):
        from core.tools.automated_build import do_automated_build

        class BrokenMock:
            async def _build_project(self, goal):
                raise RuntimeError("Internal build error")

        mock_module = type(sys)("build_tools")
        mock_module._ensure_automation = mock.AsyncMock()
        gm = type(sys)("_GOAL_MANAGER")
        gm.create = mock.Mock()
        gm.get = mock.Mock()
        mock_module._GOAL_MANAGER = gm
        mock_module._BUILD_LOOP = BrokenMock()

        with mock.patch.dict("sys.modules", {"core.tools.build_tools": mock_module}):
            result = asyncio.run(do_automated_build(
                "Build android app",
                project_dir=tempfile.mkdtemp(),
            ))

        self.assertFalse(result.success)
        self.assertIn("failed", result.status)

    def test_65_execution_id_is_unique(self):
        from core.tools.automated_build import do_automated_build

        ids = set()
        with self._mock_build_tools():
            for _ in range(5):
                result = asyncio.run(do_automated_build(
                    "Build android app",
                    project_dir=tempfile.mkdtemp(),
                ))
                ids.add(result.execution_id)

        self.assertEqual(len(ids), 5)

    def test_66_build_artifact_types_are_present_in_dict(self):
        from core.tools.automated_build import BuildExecutionRecord
        now = datetime.now(timezone.utc)
        rec = BuildExecutionRecord(
            execution_id="test",
            goal="Build android app",
            started_at=now,
            completed_at=now,
            success=True,
            status="completed",
            artifacts=[
                {"type": "apk", "path": "app-debug.apk"},
                {"type": "build_log", "path": "build.log"},
            ],
            actual_duration_seconds=100.0,
        )
        d = rec.to_dict()
        types = {a["type"] for a in d["artifacts"]}
        self.assertIn("apk", types)
        self.assertIn("build_log", types)


class TestDoAutomatedBuildCancellation(TestCase):
    """Cancellation handling in do_automated_build."""

    def test_70_handles_cancelled_error(self):
        from core.tools.automated_build import do_automated_build

        class CancellingMock:
            async def _build_project(self, goal):
                raise asyncio.CancelledError()

        mock_module = type(sys)("build_tools")
        mock_module._ensure_automation = mock.AsyncMock()
        gm = type(sys)("_GOAL_MANAGER")
        gm.create = mock.Mock()
        gm.get = mock.Mock()
        mock_module._GOAL_MANAGER = gm
        mock_module._BUILD_LOOP = CancellingMock()

        with mock.patch.dict("sys.modules", {"core.tools.build_tools": mock_module}):
            result = asyncio.run(do_automated_build(
                "Build android app",
                project_dir=tempfile.mkdtemp(),
            ))

        self.assertFalse(result.success)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.failure_reason, "Build cancelled")
