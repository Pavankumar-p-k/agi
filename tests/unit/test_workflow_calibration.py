"""Unit tests for Phase 3 X.9 WorkflowCalibrationEngine.

Tests cover: _compute_weighted_stats, _decay_confidence,
predict, recalibrate, recalibrate_all, fingerprint parsing.
"""

import time

import pytest

from core.providers.feedback.models import CalibrationConfig
from core.workflow.calibration import (
    WorkflowCalibrationEngine, WorkflowCalibrationMetrics,
    WorkflowPrediction, _compute_weighted_stats, _decay_confidence,
)
from core.workflow.learning_models import (
    RecoveryMode, WorkflowFingerprint, WorkflowOutcome,
    _parse_fingerprint_key,
)
from core.workflow.learning_store import (
    WorkflowCalibrationStore, WorkflowHistoryStore,
)


# ═════════════════════════════════════════════════════════════════════════════
# _parse_fingerprint_key
# ═════════════════════════════════════════════════════════════════════════════

class TestParseFingerprintKey:
    def test_parse_empty(self):
        assert _parse_fingerprint_key("") == {
            "task_type": "", "languages": "",
            "frameworks": "", "project_size": "",
        }

    def test_parse_task_only(self):
        r = _parse_fingerprint_key("t:build")
        assert r["task_type"] == "build"

    def test_parse_full(self):
        r = _parse_fingerprint_key("t:build|l:python|f:fastapi|s:large")
        assert r["task_type"] == "build"
        assert r["languages"] == "python"
        assert r["frameworks"] == "fastapi"
        assert r["project_size"] == "large"

    def test_parse_partial(self):
        r = _parse_fingerprint_key("t:research|s:small")
        assert r["task_type"] == "research"
        assert r["project_size"] == "small"
        assert r["languages"] == ""
        assert r["frameworks"] == ""

    def test_parse_extra_fields_ignored(self):
        r = _parse_fingerprint_key("t:build|c:medium|a:apk|r:auth")
        assert r["task_type"] == "build"
        # Extra fields like c:, a:, r: are not in the fallback dimensions


# ═════════════════════════════════════════════════════════════════════════════
# _compute_weighted_stats
# ═════════════════════════════════════════════════════════════════════════════

class TestComputeWeightedStats:
    def test_empty(self):
        metrics = _compute_weighted_stats([], CalibrationConfig())
        assert metrics.evidence_count == 0
        assert metrics.success_rate == 0.0
        assert metrics.confidence == 0.0

    def test_all_success_first_try(self):
        outcomes = [
            WorkflowOutcome(
                workflow_id=f"wf_{i}", template_id="t1",
                success=True, duration_ms=1000.0, cost=0.1, quality=0.9,
                recovery_mode=RecoveryMode.FIRST_TRY,
            )
            for i in range(10)
        ]
        metrics = _compute_weighted_stats(outcomes, CalibrationConfig(max_evidence=50))
        assert metrics.success_rate == 1.0
        assert metrics.first_try_rate == 1.0
        assert metrics.recovered_rate == 0.0
        assert metrics.failed_rate == 0.0
        assert metrics.avg_duration_ms == 1000.0
        assert metrics.evidence_count == 10

    def test_mixed_success_failure(self):
        outcomes = [
            WorkflowOutcome(workflow_id="wf_1", template_id="t1", success=True, recovery_mode=RecoveryMode.FIRST_TRY),
            WorkflowOutcome(workflow_id="wf_2", template_id="t1", success=True, recovery_mode=RecoveryMode.AFTER_RETRY),
            WorkflowOutcome(workflow_id="wf_3", template_id="t1", success=False, recovery_mode=RecoveryMode.FAILED),
            WorkflowOutcome(workflow_id="wf_4", template_id="t1", success=True, recovery_mode=RecoveryMode.FIRST_TRY),
        ]
        metrics = _compute_weighted_stats(outcomes, CalibrationConfig(max_evidence=50))
        assert metrics.success_rate == 0.75
        assert metrics.evidence_count == 4
        assert metrics.first_try_rate == 0.5
        assert metrics.recovered_rate == 0.25
        assert metrics.failed_rate == 0.25

    def test_all_failed(self):
        outcomes = [
            WorkflowOutcome(workflow_id=f"wf_{i}", template_id="t1", success=False, recovery_mode=RecoveryMode.FAILED)
            for i in range(5)
        ]
        metrics = _compute_weighted_stats(outcomes, CalibrationConfig(max_evidence=50))
        assert metrics.success_rate == 0.0
        assert metrics.failed_rate == 1.0

    def test_mixed_recovery_modes(self):
        outcomes = [
            WorkflowOutcome(workflow_id="wf_1", template_id="t1", success=True, recovery_mode=RecoveryMode.FIRST_TRY),
            WorkflowOutcome(workflow_id="wf_2", template_id="t1", success=True, recovery_mode=RecoveryMode.AFTER_RETRY),
            WorkflowOutcome(workflow_id="wf_3", template_id="t1", success=True, recovery_mode=RecoveryMode.AFTER_PROVIDER_SWAP),
            WorkflowOutcome(workflow_id="wf_4", template_id="t1", success=True, recovery_mode=RecoveryMode.AFTER_REPLAN),
            WorkflowOutcome(workflow_id="wf_5", template_id="t1", success=True, recovery_mode=RecoveryMode.AFTER_COMPENSATION),
            WorkflowOutcome(workflow_id="wf_6", template_id="t1", success=False, recovery_mode=RecoveryMode.FAILED),
        ]
        metrics = _compute_weighted_stats(outcomes, CalibrationConfig(max_evidence=50))
        assert metrics.first_try_rate == 1 / 6
        assert metrics.recovered_rate == 4 / 6  # retry + swap + replan + compensation
        assert metrics.failed_rate == 1 / 6

    def test_confidence_evidence_factor(self):
        # Few outcomes → low evidence factor
        few = [WorkflowOutcome(workflow_id=f"wf_{i}", template_id="t1", success=True, recovery_mode=RecoveryMode.FIRST_TRY) for i in range(2)]
        cfg = CalibrationConfig(max_evidence=50)
        metrics_few = _compute_weighted_stats(few, cfg)
        # evidence_factor = 2/50 = 0.04, variance with 0-variance outcomes = 1.0, stability = 1.0
        # confidence = 0.04*0.4 + 1.0*0.3 + 1.0*0.3 = 0.616
        assert 0.5 < metrics_few.confidence < 0.7

    def test_confidence_high_with_many_consistent(self):
        outcomes = [
            WorkflowOutcome(
                workflow_id=f"wf_{i}", template_id="t1",
                success=True, quality=0.9, recovery_mode=RecoveryMode.FIRST_TRY,
            )
            for i in range(40)
        ]
        cfg = CalibrationConfig(max_evidence=50)
        metrics = _compute_weighted_stats(outcomes, cfg)
        assert metrics.confidence > 0.5

    def test_variance_penalty(self):
        # High quality variance → lower confidence
        outcomes = [
            WorkflowOutcome(workflow_id=f"wf_{i}", template_id="t1",
                success=True if i < 5 else False,
                quality=0.9 if i < 5 else 0.2,
                recovery_mode=RecoveryMode.FIRST_TRY if i < 5 else RecoveryMode.FAILED,
            )
            for i in range(10)
        ]
        metrics = _compute_weighted_stats(outcomes, CalibrationConfig(max_evidence=50))
        # variance will be high → lower confidence
        assert 0.0 < metrics.confidence < 1.0

    def test_averages(self):
        outcomes = [
            WorkflowOutcome(workflow_id="wf_1", template_id="t1", success=True, duration_ms=500.0, cost=0.1, quality=0.8),
            WorkflowOutcome(workflow_id="wf_2", template_id="t1", success=True, duration_ms=1500.0, cost=0.3, quality=0.9),
        ]
        metrics = _compute_weighted_stats(outcomes, CalibrationConfig(max_evidence=50))
        assert metrics.avg_duration_ms == 1000.0
        assert metrics.avg_cost == pytest.approx(0.2)
        assert metrics.avg_quality == pytest.approx(0.85)


# ═════════════════════════════════════════════════════════════════════════════
# _decay_confidence
# ═════════════════════════════════════════════════════════════════════════════

class TestDecayConfidence:
    def test_no_decay_for_fresh(self):
        now = time.time()
        conf = _decay_confidence(0.9, now, CalibrationConfig(), now=now)
        assert conf == pytest.approx(0.9, abs=1e-3)

    def test_decay_over_time(self):
        now = time.time()
        old = now - (150 * 86400)  # 150 days
        conf = _decay_confidence(0.9, old, CalibrationConfig(half_life_days=100.0), now=now)
        assert conf < 0.9
        assert conf > 0.0

    def test_full_decay(self):
        now = time.time()
        very_old = now - (500 * 86400)  # 500 days
        conf = _decay_confidence(0.9, very_old, CalibrationConfig(half_life_days=100.0), now=now)
        assert conf == 0.0  # below minimum_weight

    def test_zero_confidence(self):
        conf = _decay_confidence(0.0, 0, CalibrationConfig())
        assert conf == 0.0

    def test_negative_confidence(self):
        conf = _decay_confidence(-0.1, 0, CalibrationConfig())
        assert conf == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# WorkflowCalibrationEngine
# ═════════════════════════════════════════════════════════════════════════════

def _make_outcome(
    wf_id: str, template_id: str = "t1",
    template_version: int = 1,
    success: bool = True,
    duration_ms: float = 1000.0,
    cost: float = 0.1,
    quality: float = 0.9,
    recovery_mode: RecoveryMode = RecoveryMode.FIRST_TRY,
    task_type: str = "build",
    languages: list[str] | None = None,
    frameworks: list[str] | None = None,
    project_size: str = "",
) -> WorkflowOutcome:
    return WorkflowOutcome(
        workflow_id=wf_id,
        template_id=template_id,
        template_version=template_version,
        fingerprint=WorkflowFingerprint(
            task_type=task_type,
            languages=languages or [],
            frameworks=frameworks or [],
            project_size=project_size,
        ),
        success=success,
        duration_ms=duration_ms,
        cost=cost,
        quality=quality,
        recovery_mode=recovery_mode,
    )


class TestWorkflowCalibrationEngine:
    @pytest.fixture
    def engine(self, tmp_path):
        db = str(tmp_path / "test_engine.db")
        hs = WorkflowHistoryStore(db_path=db)
        cs = WorkflowCalibrationStore(db_path=db)
        eng = WorkflowCalibrationEngine(
            history_store=hs, calibration_store=cs,
            config=CalibrationConfig(min_evidence=2, max_evidence=50),
        )
        yield eng
        hs.close()
        cs.close()

    # ── predict ─────────────────────────────────────────────────────

    def test_predict_no_data(self, engine):
        pred = engine.predict("t1")
        assert pred.template_id == "t1"
        assert pred.expected_success == 0.0
        assert pred.confidence == 0.0
        assert pred.evidence_count == 0

    def test_predict_after_calibration(self, engine):
        # Seed history with outcomes
        for i in range(5):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", task_type="build", project_size="large")
            )
        engine.recalibrate("t1")

        pred = engine.predict(
            "t1", task_type="build", project_size="large",
        )
        assert pred.expected_success == 1.0
        assert pred.evidence_count >= 5
        assert pred.confidence > 0.0

    def test_predict_with_fallback(self, engine):
        # Store outcomes with full fingerprint
        for i in range(5):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", task_type="build",
                              languages=["python"], frameworks=["fastapi"],
                              project_size="large")
            )
        engine.recalibrate("t1")

        # Query with extra dimension not in history — should fall back
        pred = engine.predict(
            "t1", task_type="build", languages="python",
            frameworks="fastapi", project_size="large",
        )
        # Most specific level should match
        assert pred.expected_success == 1.0
        assert pred.evidence_count >= 5

    def test_predict_fallback_to_generic(self, engine):
        # Store outcomes with only task_type
        for i in range(5):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", task_type="build")
            )
        engine.recalibrate("t1")

        pred = engine.predict(
            "t1", task_type="build", languages="python",
            frameworks="fastapi", project_size="large",
        )
        assert pred.expected_success == 1.0

    def test_predict_fallback_chain_task_only(self, engine):
        for i in range(5):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", task_type="build")
            )
        engine.recalibrate("t1")

        pred = engine.predict(
            "t1", task_type="build", languages="python",
        )
        assert pred.expected_success == 1.0

    def test_predict_different_template(self, engine):
        for i in range(5):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", template_id="t1", task_type="build")
            )
        engine.recalibrate("t1")

        pred = engine.predict("t2", task_type="build")
        assert pred.expected_success == 0.0
        assert pred.evidence_count == 0

    def test_predict_with_decayed_confidence(self, engine):
        for i in range(5):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", task_type="build")
            )
        engine.recalibrate("t1")

        # Manually age the calibration entry by 400 days
        entries = engine._calibration.list_calibrations(template_id="t1")
        for entry in entries:
            engine._calibration._get_conn().execute(
                "UPDATE workflow_calibration SET updated_at = ? WHERE id = ?",
                (time.time() - (400 * 86400), entry["id"]),
            )

        pred = engine.predict("t1", task_type="build")
        # Confidence should be zero after 400 days (half_life=100, min_weight=0.05)
        assert pred.confidence == 0.0
        assert pred.expected_success == 0.0  # zeroed when confidence is 0

    def test_predict_with_confidence_fresh(self, engine):
        for i in range(10):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", task_type="build", success=True)
            )
        engine.recalibrate("t1")

        pred = engine.predict("t1", task_type="build")
        assert pred.confidence > 0.0

    # ── recalibrate ─────────────────────────────────────────────────

    def test_recalibrate_no_outcomes(self, engine):
        count = engine.recalibrate("nonexistent")
        assert count == 0

    def test_recalibrate_single_template(self, engine):
        for i in range(5):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", task_type="build")
            )
        count = engine.recalibrate("t1")
        assert count >= 1

        entries = engine._calibration.list_calibrations(template_id="t1")
        assert len(entries) >= 1

    def test_recalibrate_with_version(self, engine):
        for i in range(3):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", template_id="t1", template_version=2,
                              task_type="build")
            )
        count = engine.recalibrate("t1", template_version=2)
        assert count >= 1

        entries = engine._calibration.list_calibrations(template_id="t1")
        for e in entries:
            assert e["template_version"] == 2

    def test_recalibrate_multiple_fingerprint_groups(self, engine):
        for i in range(3):
            engine._history.save_outcome(
                _make_outcome(f"wf_b{i}", task_type="build")
            )
        for i in range(3):
            engine._history.save_outcome(
                _make_outcome(f"wf_r{i}", task_type="research")
            )

        count = engine.recalibrate("t1")
        # Should create at least one entry per task type at (task) level
        assert count >= 2

    def test_recalibrate_insufficient_evidence(self, engine):
        engine._history.save_outcome(
            _make_outcome("wf_1", task_type="build")
        )
        count = engine.recalibrate("t1")
        # min_evidence=2, only 1 outcome → no entries
        assert count == 0

    def test_recalibrate_all(self, engine):
        for i in range(3):
            engine._history.save_outcome(
                _make_outcome(f"wf_a{i}", template_id="t1", task_type="build")
            )
        for i in range(3):
            engine._history.save_outcome(
                _make_outcome(f"wf_b{i}", template_id="t2", task_type="research")
            )

        total = engine.recalibrate_all()
        assert total >= 2

        t1_entries = engine._calibration.list_calibrations(template_id="t1")
        t2_entries = engine._calibration.list_calibrations(template_id="t2")
        assert len(t1_entries) >= 1
        assert len(t2_entries) >= 1

    # ── get_prediction (alias) ──────────────────────────────────────

    def test_get_prediction_alias(self, engine):
        for i in range(5):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", task_type="build")
            )
        engine.recalibrate("t1")

        p1 = engine.predict("t1", task_type="build")
        p2 = engine.get_prediction("t1", task_type="build")
        assert p1.expected_success == p2.expected_success
        assert p1.confidence == p2.confidence

    # ── Recovery metrics ────────────────────────────────────────────

    def test_recalibrate_stores_recovery_rates(self, engine):
        for i in range(4):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", task_type="build",
                              recovery_mode=RecoveryMode.FIRST_TRY)
            )
        engine._history.save_outcome(
            _make_outcome("wf_5", task_type="build",
                          recovery_mode=RecoveryMode.AFTER_RETRY)
        )
        engine._history.save_outcome(
            _make_outcome("wf_6", task_type="build",
                          recovery_mode=RecoveryMode.FAILED)
        )

        engine.recalibrate("t1")
        entries = engine._calibration.list_calibrations(template_id="t1")
        # Find the task-level entry
        build_entry = None
        for e in entries:
            if e["fingerprint_key"] == "t:build":
                build_entry = e
                break
        assert build_entry is not None
        assert build_entry["first_try_rate"] == pytest.approx(4.0 / 6.0, abs=0.01)
        assert build_entry["recovered_rate"] == pytest.approx(1.0 / 6.0, abs=0.01)

    def test_predict_returns_recovery_probs(self, engine):
        for i in range(5):
            engine._history.save_outcome(
                _make_outcome(f"wf_{i}", task_type="build",
                              recovery_mode=RecoveryMode.FIRST_TRY)
            )
        engine._history.save_outcome(
            _make_outcome("wf_6", task_type="build", success=False,
                          recovery_mode=RecoveryMode.FAILED)
        )

        engine.recalibrate("t1")
        pred = engine.predict("t1", task_type="build")
        assert pred.first_try_probability == pytest.approx(5.0 / 6.0, abs=0.01)
        assert pred.failed_probability == pytest.approx(1.0 / 6.0, abs=0.01)
