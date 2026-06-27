"""Unit tests for Phase 4 X.9 WorkflowExecutionRecorder.

Tests cover: outcome recording, terminal state observation,
recovery mode determination, fingerprint construction, duration
computation, error categorization, quality scoring, engine integration.
"""

import time

import pytest

from core.workflow.learning_models import (
    RecoveryMode,
    WorkflowFingerprint,
    WorkflowOutcome,
)
from core.workflow.learning_store import WorkflowHistoryStore
from core.workflow.calibration import WorkflowCalibrationEngine, WorkflowCalibrationStore
from core.workflow.models import StepStatus, WorkflowInstance, WorkflowStatus, WorkflowStep
from core.workflow.recorder import WorkflowExecutionRecorder


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


def _make_wf(
    wf_id: str = "wf_test_001",
    wf_type: str = "test_build",
    status: WorkflowStatus = WorkflowStatus.COMPLETED,
    steps: list | None = None,
    execution_context: dict | None = None,
    artifacts: list | None = None,
    created_at=None,
) -> WorkflowInstance:
    from datetime import datetime
    now = created_at or datetime.utcnow()
    return WorkflowInstance(
        workflow_id=wf_id,
        workflow_type=wf_type,
        status=status,
        steps=steps or [],
        execution_context=execution_context or {},
        artifacts=artifacts or [],
        created_at=now,
    )


def _make_step(
    tool_name: str = "build_project",
    status: StepStatus = StepStatus.COMPLETED,
    error: str | None = None,
    retry_count: int = 0,
    started_at=None,
    completed_at=None,
) -> WorkflowStep:
    from datetime import datetime
    now = datetime.utcnow()
    import uuid as _uuid
    sid = f"step_{_uuid.uuid4().hex[:8]}"
    return WorkflowStep(
        step_id=sid,
        idempotency_key=f"ik_{sid}",
        tool_name=tool_name,
        status=status,
        error=error,
        retry_count=retry_count,
        started_at=started_at or now,
        completed_at=completed_at or now,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Recorder fixture
# ═════════════════════════════════════════════════════════════════════════════


class TestWorkflowExecutionRecorder:
    @pytest.fixture
    def recorder(self, tmp_path):
        db = str(tmp_path / "test_recorder.db")
        hs = WorkflowHistoryStore(db_path=db)
        cs = WorkflowCalibrationStore(db_path=db)
        eng = WorkflowCalibrationEngine(
            history_store=hs, calibration_store=cs,
        )
        r = WorkflowExecutionRecorder(
            history_store=hs, calibration_engine=eng,
        )
        yield r
        hs.close()
        cs.close()

    @pytest.fixture
    def recorder_no_calib(self, tmp_path):
        """Recorder without calibration engine for focused tests."""
        db = str(tmp_path / "test_recorder_nc.db")
        hs = WorkflowHistoryStore(db_path=db)
        r = WorkflowExecutionRecorder(history_store=hs)
        yield r
        hs.close()

    # ── Terminal state recording ─────────────────────────────────────

    def test_record_completed(self, recorder):
        wf = _make_wf(status=WorkflowStatus.COMPLETED)
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.workflow_id == "wf_test_001"
        assert outcome.success is True
        assert outcome.recovery_mode == RecoveryMode.FIRST_TRY
        assert outcome.template_id == "test_build"

    def test_record_completed_with_retries(self, recorder):
        step = _make_step(retry_count=2, status=StepStatus.COMPLETED)
        wf = _make_wf(status=WorkflowStatus.COMPLETED, steps=[step])
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.success is True
        assert outcome.recovery_mode == RecoveryMode.AFTER_RETRY

    def test_record_failed(self, recorder):
        wf = _make_wf(status=WorkflowStatus.FAILED)
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.success is False
        assert outcome.recovery_mode == RecoveryMode.FAILED

    def test_record_cancelled(self, recorder):
        wf = _make_wf(status=WorkflowStatus.CANCELLED)
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.success is False
        assert outcome.recovery_mode == RecoveryMode.FAILED

    def test_record_compensated(self, recorder):
        wf = _make_wf(status=WorkflowStatus.COMPENSATED)
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.success is False
        assert outcome.recovery_mode == RecoveryMode.AFTER_COMPENSATION

    def test_record_compensation_failed(self, recorder):
        wf = _make_wf(status=WorkflowStatus.COMPENSATION_FAILED)
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.success is False
        assert outcome.recovery_mode == RecoveryMode.FAILED

    # ── Skip non-terminal ────────────────────────────────────────────

    def test_skip_pending(self, recorder):
        wf = _make_wf(status=WorkflowStatus.PENDING)
        outcome = recorder.record_workflow(wf)
        assert outcome is None

    def test_skip_running(self, recorder):
        wf = _make_wf(status=WorkflowStatus.RUNNING)
        outcome = recorder.record_workflow(wf)
        assert outcome is None

    # ── Append-only guard ────────────────────────────────────────────

    def test_skip_already_recorded(self, recorder):
        wf = _make_wf(status=WorkflowStatus.COMPLETED)
        outcome1 = recorder.record_workflow(wf)
        assert outcome1 is not None
        outcome2 = recorder.record_workflow(wf)
        assert outcome2 is None

    # ── Fingerprint construction ─────────────────────────────────────

    def test_fingerprint_from_context(self, recorder):
        ctx = {
            "task_type": "build",
            "languages": ["python", "typescript"],
            "frameworks": ["fastapi"],
            "project_size": "large",
        }
        wf = _make_wf(execution_context=ctx)
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.fingerprint is not None
        assert outcome.fingerprint.task_type == "build"
        assert outcome.fingerprint.project_size == "large"

    def test_fingerprint_none_when_empty_context(self, recorder):
        wf = _make_wf(execution_context={})
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.fingerprint is None
        assert outcome.fingerprint_key == ""

    def test_fingerprint_partial_context(self, recorder):
        ctx = {"task_type": "research"}
        wf = _make_wf(execution_context=ctx)
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.fingerprint is not None
        assert outcome.fingerprint_key == "t:research"

    # ── Template version from context ────────────────────────────────

    def test_template_version_from_context(self, recorder):
        wf = _make_wf(execution_context={"template_version": 3})
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.template_version == 3

    def test_template_version_defaults_to_1(self, recorder):
        wf = _make_wf()
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.template_version == 1

    # ── Duration computation ─────────────────────────────────────────

    def test_duration_with_start_time(self, recorder):
        wf = _make_wf(status=WorkflowStatus.COMPLETED)
        start = time.time() - 2.5
        outcome = recorder.record_workflow(wf, start_time=start)
        assert outcome is not None
        assert outcome.duration_ms >= 2000.0
        assert outcome.duration_ms < 5000.0

    def test_duration_from_step_timestamps(self, recorder):
        from datetime import datetime, timedelta
        base = datetime.utcnow()
        step = _make_step(
            started_at=base - timedelta(seconds=3),
            completed_at=base,
        )
        wf = _make_wf(steps=[step])
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.duration_ms >= 2500.0
        assert outcome.duration_ms < 4000.0

    def test_duration_zero_when_no_steps(self, recorder):
        wf = _make_wf()
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.duration_ms == 0.0

    # ── Error categories ─────────────────────────────────────────────

    def test_error_categories_empty_when_no_failures(self, recorder):
        wf = _make_wf(status=WorkflowStatus.COMPLETED)
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.error_categories == []

    def test_error_categories_from_failed_steps(self, recorder):
        step = _make_step(
            tool_name="build_project",
            status=StepStatus.FAILED,
            error="Compilation failed: syntax error in main.py",
        )
        wf = _make_wf(status=WorkflowStatus.FAILED, steps=[step])
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert "build_project" in outcome.error_categories
        assert "syntax" in outcome.error_categories

    def test_error_categories_patterns(self, recorder):
        step = _make_step(
            tool_name="run_tests",
            status=StepStatus.FAILED,
            error="Timeout: test suite exceeded 30s limit",
        )
        wf = _make_wf(status=WorkflowStatus.FAILED, steps=[step])
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert "run_tests" in outcome.error_categories
        assert "timeout" in outcome.error_categories

    def test_error_categories_dedup(self, recorder):
        s1 = _make_step(tool_name="build", status=StepStatus.FAILED, error="build failed")
        s2 = _make_step(tool_name="build", status=StepStatus.FAILED, error="build failed again")
        wf = _make_wf(status=WorkflowStatus.FAILED, steps=[s1, s2])
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.error_categories == ["build"]

    # ── Quality scoring ──────────────────────────────────────────────

    def test_quality_completed_first_try(self, recorder):
        wf = _make_wf(status=WorkflowStatus.COMPLETED)
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.quality == 1.0  # 0.6 + 0.2 + 0.2

    def test_quality_completed_with_retry(self, recorder):
        step = _make_step(retry_count=1)
        wf = _make_wf(steps=[step])
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.quality == 0.8  # 0.6 + 0.0 + 0.2

    def test_quality_failed(self, recorder):
        wf = _make_wf(status=WorkflowStatus.FAILED)
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.quality == 0.2  # 0.0 + 0.0 + 0.2

    # ── Provider summary ──────────────────────────────────────────────

    def test_provider_summary_from_entries(self, recorder):
        provider_entries = [
            {"provider": "forge", "capability": "coding",
             "duration_ms": 18342.0, "success": True, "retries": 0, "cost": 0.0},
            {"provider": "codex", "capability": "security_review",
             "duration_ms": 7421.0, "success": True, "retries": 1, "cost": 0.02},
        ]
        wf = _make_wf(execution_context={
            "provider_entries": provider_entries,
        })
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert len(outcome.provider_summary) == 2
        assert outcome.provider_summary[0]["provider"] == "forge"
        assert outcome.provider_summary[0]["duration_ms"] == 18342.0
        assert outcome.provider_summary[1]["retries"] == 1

    def test_provider_summary_empty_when_no_context(self, recorder):
        wf = _make_wf()
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert outcome.provider_summary == []

    def test_provider_summary_converts_old_format(self, recorder):
        wf = _make_wf(execution_context={
            "provider_summary": {"forge": True, "codex": True},
        })
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert len(outcome.provider_summary) == 2

    # ── record_workflow_by_id ────────────────────────────────────────

    def test_record_by_id(self, recorder, tmp_path):
        from core.workflow.storage import WorkflowStore
        store = WorkflowStore(
            db_path=str(tmp_path / "by_id_workflow.db"),
        )
        wf = _make_wf(
            wf_id="wf_by_id", status=WorkflowStatus.COMPLETED,
        )
        store.create_workflow(wf)

        outcome = recorder.record_workflow_by_id("wf_by_id", store=store)
        assert outcome is not None
        assert outcome.workflow_id == "wf_by_id"
        assert outcome.success is True

    def test_record_by_id_not_found(self, recorder):
        outcome = recorder.record_workflow_by_id("wf_nonexistent")
        assert outcome is None

    # ── record_multiple (audit) ──────────────────────────────────────

    def test_record_multiple_audit(self, recorder, tmp_path):
        from core.workflow.storage import WorkflowStore
        store = WorkflowStore(
            db_path=str(tmp_path / "audit_workflow.db"),
        )

        for i in range(3):
            wf = _make_wf(
                wf_id=f"wf_audit_{i}",
                status=WorkflowStatus.COMPLETED,
            )
            store.create_workflow(wf)

        count = recorder.record_multiple(store=store)
        assert count == 3

    def test_record_multiple_skips_existing(self, recorder, tmp_path):
        from core.workflow.storage import WorkflowStore
        store = WorkflowStore(
            db_path=str(tmp_path / "dup_workflow.db"),
        )

        wf = _make_wf(
            wf_id="wf_dup",
            status=WorkflowStatus.COMPLETED,
        )
        store.create_workflow(wf)
        count1 = recorder.record_multiple(store=store)
        assert count1 == 1

        count2 = recorder.record_multiple(store=store)
        assert count2 == 0  # already recorded

    # ── Artifact extraction ──────────────────────────────────────────

    def test_artifacts_from_workflow(self, recorder):
        wf = _make_wf(artifacts=[
            {"artifact_id": "art_001"},
            {"id": "art_002"},
            "plain_string_id",
        ])
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        assert "art_001" in outcome.artifacts
        assert "art_002" in outcome.artifacts
        assert "plain_string_id" in outcome.artifacts

    # ── Edge cases ───────────────────────────────────────────────────

    def test_record_none_recorder(self, recorder_no_calib):
        """Should not crash when calibration engine is not configured."""
        wf = _make_wf()
        outcome = recorder_no_calib.record_workflow(wf)
        assert outcome is not None

    def test_persisted_to_history(self, recorder):
        wf = _make_wf()
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        loaded = recorder._history.get_outcome(wf.workflow_id)
        assert loaded is not None
        assert loaded.success is True
        assert loaded.template_id == "test_build"

    def test_recalibration_triggered(self, recorder):
        # Override config to accept 1 evidence point
        from core.providers.feedback.models import CalibrationConfig
        recorder._calibration._config = CalibrationConfig(
            min_evidence=1, max_evidence=50,
        )
        wf = _make_wf()
        outcome = recorder.record_workflow(wf)
        assert outcome is not None
        # Verify calibration was created
        calib = recorder._calibration._calibration.get_calibration(
            template_id="test_build",
        )
        assert calib is not None
        assert calib["evidence_count"] >= 1
