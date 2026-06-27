"""Unit tests for Phase 2 X.9 stores.

Tests cover: WorkflowHistoryStore, WorkflowCalibrationStore,
fingerprint fallback, aggregation, append-only semantics.
"""

import json
import math
import time

import pytest

from core.workflow.learning_models import (
    RecoveryMode, WorkflowFingerprint, WorkflowOutcome,
    _FINGERPRINT_FALLBACK_CHAIN, _fingerprint_fallback_key,
)
from core.workflow.learning_store import (
    WorkflowHistoryStore, WorkflowCalibrationStore,
)


# ═════════════════════════════════════════════════════════════════════════════
# Fingerprint fallback helpers
# ═════════════════════════════════════════════════════════════════════════════

class TestFingerprintFallback:
    def test_fallback_chain_structure(self):
        assert len(_FINGERPRINT_FALLBACK_CHAIN) == 5
        assert _FINGERPRINT_FALLBACK_CHAIN[0] == (4, 3, 2, 1)
        assert _FINGERPRINT_FALLBACK_CHAIN[-1] == (0, 0, 0, 0)

    def test_fallback_key_empty(self):
        assert _fingerprint_fallback_key("") == ""

    def test_fallback_key_task_only(self):
        key = _fingerprint_fallback_key("build")
        assert key == "t:build"

    def test_fallback_key_full(self):
        key = _fingerprint_fallback_key(
            task_type="build", languages="python,typescript",
            frameworks="fastapi", project_size="large",
        )
        assert "t:build" in key
        assert "l:python,typescript" in key or "l:typescript,python" in key
        assert "f:fastapi" in key
        assert "s:large" in key

    def test_fallback_key_sorted(self):
        key = _fingerprint_fallback_key(
            task_type="build", languages="typescript,python",
        )
        assert "l:python,typescript" in key

    def test_fallback_key_whitespace_stripped(self):
        key = _fingerprint_fallback_key(
            task_type="build", languages=" python , typescript ",
        )
        assert "l:python,typescript" in key

    def test_fallback_key_no_languages_when_all_blank(self):
        key = _fingerprint_fallback_key(
            task_type="build", languages="  ,  ",
        )
        assert "l:" not in key
        assert key == "t:build"

    def test_fallback_key_match_format(self):
        """Partial key should match the same format as full context_key."""
        fp = WorkflowFingerprint(
            task_type="build", languages=["python", "typescript"],
        )
        partial = _fingerprint_fallback_key(
            task_type="build", languages="python,typescript",
        )
        assert fp.context_key() == partial


# ═════════════════════════════════════════════════════════════════════════════
# WorkflowHistoryStore
# ═════════════════════════════════════════════════════════════════════════════

class TestWorkflowHistoryStore:
    @pytest.fixture
    def store(self, tmp_path):
        db = str(tmp_path / "test_history.db")
        s = WorkflowHistoryStore(db_path=db)
        yield s
        s.close()

    def _make_outcome(
        self, wf_id: str, success: bool = True,
        template_id: str = "test_template",
        template_version: int = 1,
        duration_ms: float = 1000.0,
        cost: float = 0.0,
        quality: float = 0.9,
        recovery_mode: RecoveryMode = RecoveryMode.FIRST_TRY,
        artifacts: list[str] | None = None,
        error_categories: list[str] | None = None,
        task_type: str = "build",
    ) -> WorkflowOutcome:
        return WorkflowOutcome(
            workflow_id=wf_id,
            template_id=template_id,
            template_version=template_version,
            fingerprint=WorkflowFingerprint(task_type=task_type),
            success=success,
            duration_ms=duration_ms,
            cost=cost,
            quality=quality,
            recovery_mode=recovery_mode,
            artifacts=artifacts or [],
            error_categories=error_categories or [],
        )

    def test_save_and_get(self, store):
        outcome = self._make_outcome("wf_001")
        store.save_outcome(outcome)
        loaded = store.get_outcome("wf_001")
        assert loaded is not None
        assert loaded.workflow_id == "wf_001"
        assert loaded.success is True
        assert loaded.template_id == "test_template"

    def test_get_not_found(self, store):
        assert store.get_outcome("nonexistent") is None

    def test_append_only_rejects_duplicate(self, store):
        outcome = self._make_outcome("wf_dup")
        store.save_outcome(outcome)
        with pytest.raises(ValueError, match="already exists"):
            store.save_outcome(outcome)

    def test_save_direct(self, store):
        store.save_outcome_direct(
            workflow_id="wf_direct",
            template_id="test",
            template_version=1,
            fingerprint_key="t:build",
            outcome_json='{"success": true}',
            timestamp=1000.0,
            success=True,
            recovery_mode="FIRST_TRY",
        )
        loaded = store.get_outcome("wf_direct")
        assert loaded is not None
        assert loaded.workflow_id == "wf_direct"

    def test_save_direct_rejects_duplicate(self, store):
        store.save_outcome_direct(workflow_id="wf_dup2")
        with pytest.raises(ValueError, match="already exists"):
            store.save_outcome_direct(workflow_id="wf_dup2")

    def test_query_by_template_id(self, store):
        store.save_outcome(self._make_outcome("wf_1", template_id="t1"))
        store.save_outcome(self._make_outcome("wf_2", template_id="t2"))
        store.save_outcome(self._make_outcome("wf_3", template_id="t1"))

        results = store.get_outcomes(template_id="t1")
        assert len(results) == 2
        assert {r.workflow_id for r in results} == {"wf_1", "wf_3"}

    def test_query_by_template_version(self, store):
        store.save_outcome(self._make_outcome("wf_1", template_version=1))
        store.save_outcome(self._make_outcome("wf_2", template_version=2))

        results = store.get_outcomes(template_version=2)
        assert len(results) == 1
        assert results[0].workflow_id == "wf_2"

    def test_query_by_success(self, store):
        store.save_outcome(self._make_outcome("wf_s1", success=True))
        store.save_outcome(self._make_outcome("wf_s2", success=True))
        store.save_outcome(self._make_outcome("wf_f1", success=False))

        results = store.get_outcomes(success=True)
        assert len(results) == 2

        results_fail = store.get_outcomes(success=False)
        assert len(results_fail) == 1

    def test_query_by_recovery_mode(self, store):
        store.save_outcome(self._make_outcome("wf_1", recovery_mode=RecoveryMode.FIRST_TRY))
        store.save_outcome(self._make_outcome("wf_2", recovery_mode=RecoveryMode.AFTER_RETRY))

        results = store.get_outcomes(recovery_mode="FIRST_TRY")
        assert len(results) == 1
        assert results[0].workflow_id == "wf_1"

    def test_query_by_fingerprint_key(self, store):
        o1 = self._make_outcome("wf_1", task_type="build")
        o2 = self._make_outcome("wf_2", task_type="research")
        store.save_outcome(o1)
        store.save_outcome(o2)

        results = store.get_outcomes(fingerprint_key=o1.fingerprint_key)
        assert len(results) == 1
        assert results[0].workflow_id == "wf_1"

    def test_query_date_range(self, store):
        store.save_outcome(self._make_outcome("wf_1"))
        store.save_outcome(self._make_outcome("wf_2"))

        now = time.time()
        results = store.get_outcomes(min_timestamp=0, max_timestamp=now + 3600)
        assert len(results) == 2

    def test_query_with_pagination(self, store):
        for i in range(10):
            store.save_outcome(self._make_outcome(f"wf_{i}"))

        page1 = store.get_outcomes(limit=3, offset=0)
        assert len(page1) == 3

        page2 = store.get_outcomes(limit=3, offset=3)
        assert len(page2) == 3

        # IDs should not overlap across pages
        page1_ids = {r.workflow_id for r in page1}
        page2_ids = {r.workflow_id for r in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_count(self, store):
        store.save_outcome(self._make_outcome("wf_1", template_id="t1"))
        store.save_outcome(self._make_outcome("wf_2", template_id="t1"))
        store.save_outcome(self._make_outcome("wf_3", template_id="t2"))

        assert store.count_outcomes() == 3
        assert store.count_outcomes(template_id="t1") == 2
        assert store.count_outcomes(template_id="t2") == 1
        assert store.count_outcomes(template_id="nonexistent") == 0

    def test_count_by_success(self, store):
        store.save_outcome(self._make_outcome("wf_1", success=True))
        store.save_outcome(self._make_outcome("wf_2", success=False))
        store.save_outcome(self._make_outcome("wf_3", success=True))

        assert store.count_outcomes(success=True) == 2
        assert store.count_outcomes(success=False) == 1

    def test_compute_stats_empty(self, store):
        stats = store.compute_stats("nonexistent")
        assert stats["total"] == 0
        assert stats["success_rate"] == 0.0

    def test_compute_stats_all_success(self, store):
        for i in range(5):
            store.save_outcome(self._make_outcome(f"wf_s{i}", success=True))

        stats = store.compute_stats("test_template")
        assert stats["total"] == 5
        assert stats["success_count"] == 5
        assert stats["success_rate"] == 1.0
        assert stats["avg_duration_ms"] == 1000.0

    def test_compute_stats_mixed(self, store):
        store.save_outcome(self._make_outcome("wf_1", success=True, duration_ms=500.0, quality=0.9, cost=0.1))
        store.save_outcome(self._make_outcome("wf_2", success=True, duration_ms=1500.0, quality=0.8, cost=0.2))
        store.save_outcome(self._make_outcome("wf_3", success=False, duration_ms=2000.0, quality=0.3, cost=0.5))

        stats = store.compute_stats("test_template")
        assert stats["total"] == 3
        assert stats["success_count"] == 2
        assert stats["success_rate"] == 2.0 / 3.0
        assert stats["avg_duration_ms"] == (500 + 1500 + 2000) / 3
        assert stats["avg_cost"] == pytest.approx((0.1 + 0.2 + 0.5) / 3)
        assert stats["avg_quality"] == pytest.approx((0.9 + 0.8 + 0.3) / 3)

    def test_compute_stats_recovery_counts(self, store):
        store.save_outcome(self._make_outcome("wf_1", recovery_mode=RecoveryMode.FIRST_TRY))
        store.save_outcome(self._make_outcome("wf_2", recovery_mode=RecoveryMode.FIRST_TRY))
        store.save_outcome(self._make_outcome("wf_3", recovery_mode=RecoveryMode.AFTER_RETRY))
        store.save_outcome(self._make_outcome("wf_4", recovery_mode=RecoveryMode.AFTER_PROVIDER_SWAP))

        stats = store.compute_stats("test_template")
        assert stats["recovery_counts"]["FIRST_TRY"] == 2
        assert stats["recovery_counts"]["AFTER_RETRY"] == 1
        assert stats["recovery_counts"]["AFTER_PROVIDER_SWAP"] == 1

    def test_compute_stats_error_categories(self, store):
        store.save_outcome(self._make_outcome("wf_1", error_categories=["timeout"]))
        store.save_outcome(self._make_outcome("wf_2", error_categories=["build_error", "timeout"]))

        stats = store.compute_stats("test_template")
        assert "timeout" in stats["error_categories"]
        assert "build_error" in stats["error_categories"]

    def test_clear(self, store):
        store.save_outcome(self._make_outcome("wf_1"))
        store.save_outcome(self._make_outcome("wf_2"))
        assert store.count_outcomes() == 2
        store.clear()
        assert store.count_outcomes() == 0


# ═════════════════════════════════════════════════════════════════════════════
# WorkflowCalibrationStore
# ═════════════════════════════════════════════════════════════════════════════

class TestWorkflowCalibrationStore:
    @pytest.fixture
    def store(self, tmp_path):
        db = str(tmp_path / "test_calibration.db")
        s = WorkflowCalibrationStore(db_path=db)
        yield s
        s.close()

    def test_save_and_get(self, store):
        store.save_calibration(
            template_id="build_template", template_version=1,
            fingerprint_key="t:build|s:large",
            task_type="build", project_size="large",
            success_rate=0.95, avg_duration_ms=120000.0,
            avg_cost=0.15, avg_quality=0.88,
            first_try_rate=0.75, recovered_rate=0.15,
            confidence=0.85, evidence_count=20,
        )
        cal = store.get_calibration(
            template_id="build_template", template_version=1,
            fingerprint_key="t:build|s:large",
        )
        assert cal is not None
        assert cal["success_rate"] == 0.95
        assert cal["evidence_count"] == 20
        assert cal["avg_duration_ms"] == 120000.0

    def test_get_not_found(self, store):
        assert store.get_calibration("nonexistent") is None

    def test_save_replaces_existing(self, store):
        store.save_calibration(
            template_id="t1", fingerprint_key="k1",
            success_rate=0.80, evidence_count=10,
        )
        store.save_calibration(
            template_id="t1", fingerprint_key="k1",
            success_rate=0.90, evidence_count=20,
        )
        cal = store.get_calibration(template_id="t1", fingerprint_key="k1")
        assert cal["success_rate"] == 0.90
        assert cal["evidence_count"] == 20

    def test_list_calibrations(self, store):
        store.save_calibration(
            template_id="t1", fingerprint_key="k1",
            success_rate=0.9, evidence_count=10,
        )
        store.save_calibration(
            template_id="t1", fingerprint_key="k2",
            success_rate=0.8, evidence_count=5,
        )
        store.save_calibration(
            template_id="t2", fingerprint_key="k3",
            success_rate=0.7, evidence_count=3,
        )

        all_cals = store.list_calibrations()
        assert len(all_cals) == 3

        t1_cals = store.list_calibrations(template_id="t1")
        assert len(t1_cals) == 2

    def test_list_calibrations_ordered_by_evidence(self, store):
        store.save_calibration(template_id="t1", fingerprint_key="k1", success_rate=0.9, evidence_count=5)
        store.save_calibration(template_id="t1", fingerprint_key="k2", success_rate=0.8, evidence_count=20)

        cals = store.list_calibrations(template_id="t1")
        assert cals[0]["evidence_count"] >= cals[1]["evidence_count"]

    def test_get_summary(self, store):
        store.save_calibration(
            template_id="t1", fingerprint_key="k1",
            success_rate=0.95, avg_duration_ms=1000.0,
            avg_cost=0.1, avg_quality=0.9,
            confidence=0.85, evidence_count=20,
        )
        summary = store.get_summary()
        assert len(summary) == 1
        assert summary[0]["template_id"] == "t1"
        assert summary[0]["success_rate"] == 0.95
        assert summary[0]["confidence"] == 0.85
        assert "avg_duration_ms" in summary[0]

    def test_clear(self, store):
        store.save_calibration(template_id="t1", fingerprint_key="k1")
        assert len(store.list_calibrations()) == 1
        store.clear()
        assert len(store.list_calibrations()) == 0

    # ── Fallback ────────────────────────────────────────────────────

    def test_fallback_exact_match(self, store):
        store.save_calibration(
            template_id="t1", fingerprint_key="t:build|l:python",
            task_type="build", languages="python",
            success_rate=0.95, evidence_count=20,
        )
        cal = store.get_calibration_fallback(
            template_id="t1", task_type="build", languages="python",
        )
        assert cal is not None
        assert cal["success_rate"] == 0.95

    def test_fallback_task_language_only(self, store):
        store.save_calibration(
            template_id="t1", fingerprint_key="t:build|l:python",
            task_type="build", languages="python",
            success_rate=0.90, evidence_count=10,
        )
        cal = store.get_calibration_fallback(
            template_id="t1", task_type="build", languages="python",
            frameworks="fastapi", project_size="large",
        )
        assert cal is not None
        assert cal["success_rate"] == 0.90

    def test_fallback_task_only(self, store):
        store.save_calibration(
            template_id="t1", fingerprint_key="t:build",
            task_type="build",
            success_rate=0.80, evidence_count=5,
        )
        cal = store.get_calibration_fallback(
            template_id="t1", task_type="build",
            languages="python", frameworks="fastapi",
        )
        assert cal is not None
        assert cal["success_rate"] == 0.80

    def test_fallback_generic(self, store):
        store.save_calibration(
            template_id="t1", fingerprint_key="",
            task_type="",
            success_rate=0.70, evidence_count=50,
        )
        cal = store.get_calibration_fallback(
            template_id="t1", task_type="build",
            languages="python", frameworks="fastapi", project_size="large",
        )
        assert cal is not None
        assert cal["success_rate"] == 0.70

    def test_fallback_no_match(self, store):
        cal = store.get_calibration_fallback(
            template_id="nonexistent", task_type="build",
        )
        assert cal is None

    def test_fallback_prefers_most_specific(self, store):
        store.save_calibration(
            template_id="t1", fingerprint_key="t:build|l:python|f:fastapi|s:large",
            task_type="build", languages="python",
            frameworks="fastapi", project_size="large",
            success_rate=0.99, evidence_count=30,
        )
        store.save_calibration(
            template_id="t1", fingerprint_key="t:build",
            task_type="build",
            success_rate=0.70, evidence_count=50,
        )
        cal = store.get_calibration_fallback(
            template_id="t1", task_type="build",
            languages="python", frameworks="fastapi", project_size="large",
        )
        assert cal is not None
        assert cal["success_rate"] == 0.99

    def test_fallback_different_template(self, store):
        store.save_calibration(
            template_id="t1", fingerprint_key="t:build",
            task_type="build",
            success_rate=0.80, evidence_count=10,
        )
        cal = store.get_calibration_fallback(template_id="t2")
        assert cal is None

    def test_fallback_different_version(self, store):
        store.save_calibration(
            template_id="t1", template_version=1,
            fingerprint_key="t:build",
            task_type="build",
            success_rate=0.80, evidence_count=10,
        )
        cal = store.get_calibration_fallback(
            template_id="t1", template_version=2, task_type="build",
        )
        assert cal is None

    def test_fallback_with_languages_only(self, store):
        """Should match at (task + lang) level when more specific fails."""
        store.save_calibration(
            template_id="t1", fingerprint_key="t:build|l:python",
            task_type="build", languages="python",
            success_rate=0.90, evidence_count=10,
        )
        cal = store.get_calibration_fallback(
            template_id="t1", task_type="build", languages="python",
            frameworks="fastapi",
        )
        assert cal is not None
        assert cal["success_rate"] == 0.90


# ═════════════════════════════════════════════════════════════════════════════
# Integration: History → Calibration workflow
# ═════════════════════════════════════════════════════════════════════════════

class TestHistoryToCalibrationFlow:
    @pytest.fixture
    def history(self, tmp_path):
        db = str(tmp_path / "test_integration.db")
        s = WorkflowHistoryStore(db_path=db)
        yield s
        s.close()

    @pytest.fixture
    def calibration(self, tmp_path):
        db = str(tmp_path / "test_integration.db")
        s = WorkflowCalibrationStore(db_path=db)
        yield s
        s.close()

    def test_compute_stats_then_store_calibration(self, history, calibration):
        for i in range(10):
            history.save_outcome(WorkflowOutcome(
                workflow_id=f"wf_{i}",
                template_id="build_template",
                template_version=1,
                fingerprint=WorkflowFingerprint(task_type="build"),
                success=True,
                duration_ms=100000.0,
                cost=0.10,
                quality=0.85,
            ))

        stats = history.compute_stats("build_template")
        calibration.save_calibration(
            template_id="build_template",
            template_version=1,
            fingerprint_key="t:build",
            task_type="build",
            success_rate=stats["success_rate"],
            avg_duration_ms=stats["avg_duration_ms"],
            avg_cost=stats["avg_cost"],
            avg_quality=stats["avg_quality"],
            first_try_rate=0.0, recovered_rate=0.0,
            confidence=0.9,
            evidence_count=stats["total"],
        )

        cal = calibration.get_calibration(
            template_id="build_template",
            template_version=1,
            fingerprint_key="t:build",
        )
        assert cal is not None
        assert cal["success_rate"] == 1.0
        assert cal["evidence_count"] == 10
        assert cal["avg_duration_ms"] == 100000.0
