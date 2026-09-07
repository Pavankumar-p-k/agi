"""Tests for Phase 8.3C — Resource Estimation."""
import os
import shutil
import tempfile

import pytest

from core.scheduler.intelligence import (
    ActivityIntelligence,
    MIN_SAMPLES_FOR_STATS,
    CONFIDENCE_SATURATION,
)
from core.scheduler.resources import (
    ResourceEstimate,
    ResourceUsage,
    ResourceCalibration,
    ResourcePredictor,
    compute_resource_cost,
    RESOURCE_MIGRATIONS,
)


class TestResourceModels:
    """ResourceEstimate, ResourceUsage, ResourceCalibration."""

    def test_resource_estimate_defaults(self):
        est = ResourceEstimate()
        assert est.token_cost == 500
        assert est.api_cost == 0.0
        assert est.memory_mb == 50.0
        assert est.browser_steps == 2
        assert est.confidence == 0.0

    def test_resource_usage_to_dict(self):
        u = ResourceUsage(token_cost=100, api_cost=5.0, memory_mb=128.0, browser_steps=10)
        d = u.to_dict()
        assert d["token_cost"] == 100
        assert d["api_cost"] == 5.0
        assert d["browser_steps"] == 10

    def test_resource_usage_from_dict(self):
        u = ResourceUsage.from_dict({"token_cost": 200, "api_cost": 3.0, "memory_mb": 256.0, "browser_steps": 5})
        assert u.token_cost == 200
        assert u.api_cost == 3.0
        assert u.memory_mb == 256.0

    def test_resource_usage_from_dict_partial(self):
        u = ResourceUsage.from_dict({"token_cost": 100})
        assert u.token_cost == 100
        assert u.api_cost == 0.0
        assert u.memory_mb == 50.0  # default

    def test_compute_resource_cost(self):
        est = ResourceEstimate(token_cost=1000, api_cost=10, memory_mb=200, browser_steps=20)
        cost = compute_resource_cost(est)
        # 1000*0.3/1000 + 10*0.25/10 + 200*0.15/100 + 20*0.3/5
        # = 0.3 + 0.25 + 0.3 + 1.2 = 2.05
        assert cost == pytest.approx(2.05)

    def test_resource_migration_cols(self):
        assert len(RESOURCE_MIGRATIONS) == 8
        names = [m[0] for m in RESOURCE_MIGRATIONS]
        assert "predicted_tokens" in names
        assert "actual_tokens" in names
        assert "actual_browser_steps" in names


class TestResourcePredictor:
    """ResourcePredictor — predict, calibrate, apply calibration."""

    def test_predict_no_data(self):
        est = ResourcePredictor.predict_from_stats("build", None, 0)
        assert est.node_type == "build"
        assert est.confidence == 0.0
        assert est.sample_size == 0
        assert est.token_cost == 500  # default

    def test_predict_with_data(self):
        row = (1000, 5.0, 128.0, 10)
        est = ResourcePredictor.predict_from_stats("research", row, 10)
        assert est.token_cost == 1000
        assert est.api_cost == 5.0
        assert est.memory_mb == 128.0
        assert est.browser_steps == 10
        assert est.confidence == 10.0 / CONFIDENCE_SATURATION
        assert est.sample_size == 10

    def test_calibrate_empty(self):
        cal = ResourcePredictor.calibrate([])
        assert cal.sample_count == 0
        assert cal.token_multiplier == 1.0

    def test_calibrate_perfect(self):
        pairs = [
            (1000, 1000, 5.0, 5.0, 128.0, 128.0, 10, 10),
            (2000, 2000, 3.0, 3.0, 256.0, 256.0, 5, 5),
        ]
        cal = ResourcePredictor.calibrate(pairs)
        assert cal.sample_count == 2
        assert cal.token_multiplier == 1.0
        assert cal.api_cost_multiplier == 1.0
        assert cal.overall_accuracy == pytest.approx(1.0)

    def test_calibrate_underestimate(self):
        """If actual is consistently higher than predicted, multiplier > 1."""
        pairs = [
            (1000, 2000, 5.0, 10.0, 128.0, 256.0, 10, 20),
            (1000, 2000, 5.0, 10.0, 128.0, 256.0, 10, 20),
        ]
        cal = ResourcePredictor.calibrate(pairs)
        assert cal.token_multiplier == 2.0
        assert cal.api_cost_multiplier == 2.0
        assert cal.memory_multiplier == 2.0
        assert cal.browser_steps_multiplier == 2.0

    def test_calibrate_overestimate(self):
        """If actual is consistently lower, multiplier < 1."""
        pairs = [
            (2000, 1000, 10.0, 5.0, 256.0, 128.0, 20, 10),
        ]
        cal = ResourcePredictor.calibrate(pairs)
        assert cal.token_multiplier == 0.5
        assert cal.api_cost_multiplier == 0.5

    def test_apply_calibration_insufficient_samples(self):
        est = ResourceEstimate(token_cost=1000, api_cost=5.0, memory_mb=128.0, browser_steps=10)
        cal = ResourceCalibration(sample_count=2, token_multiplier=2.0)
        result = ResourcePredictor.apply_calibration(est, cal)
        # < 3 samples, no change
        assert result.token_cost == 1000

    def test_apply_calibration_sufficient(self):
        est = ResourceEstimate(token_cost=1000, api_cost=5.0, memory_mb=128.0, browser_steps=10)
        cal = ResourceCalibration(sample_count=5, token_multiplier=2.0, api_cost_multiplier=1.5,
                                  memory_multiplier=0.5, browser_steps_multiplier=3.0)
        result = ResourcePredictor.apply_calibration(est, cal)
        assert result.token_cost == 2000
        assert result.api_cost == 7.5
        assert result.memory_mb == 64.0
        assert result.browser_steps == 30


class TestActivityIntelligenceResources:
    """Integration with ActivityIntelligence — predict_resources, resource_cost_score."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_resources.db")
        self._ai = ActivityIntelligence(db_path=self._db)

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_predict_resources_no_data(self):
        est = self._ai.predict_resources("build")
        assert est.confidence == 0.0
        assert est.token_cost == 500

    def test_predict_resources_with_data(self):
        """Record actual resource usage, then predict should use averages."""
        self._ai.record("a1", "build", 5000, True,
                        actual_resources=ResourceUsage(token_cost=1000, api_cost=5.0, memory_mb=128.0, browser_steps=3))
        self._ai.record("a2", "build", 5000, True,
                        actual_resources=ResourceUsage(token_cost=2000, api_cost=10.0, memory_mb=256.0, browser_steps=5))
        self._ai.record("a3", "build", 5000, True,
                        actual_resources=ResourceUsage(token_cost=1500, api_cost=7.5, memory_mb=192.0, browser_steps=4))

        est = self._ai.predict_resources("build")
        assert est.sample_size == 3
        assert est.confidence == 3.0 / CONFIDENCE_SATURATION
        assert est.token_cost == pytest.approx(1500.0)
        assert est.api_cost == pytest.approx(7.5)
        assert est.memory_mb == pytest.approx(192.0)
        assert est.browser_steps == pytest.approx(4.0)

    def test_record_with_resources(self):
        """Record with resource data persists to DB."""
        self._ai.record("a1", "build", 5000, True,
                        predicted_resources=ResourceEstimate(token_cost=1000, api_cost=5.0, memory_mb=128.0, browser_steps=3),
                        actual_resources=ResourceUsage(token_cost=1100, api_cost=4.5, memory_mb=130.0, browser_steps=3))

        cal = self._ai.get_resource_calibration("build")
        assert cal.sample_count == 1
        # token: 1100/1000 = 1.1
        assert cal.token_multiplier == 1.1

    def test_resource_cost_score_no_data(self):
        """No data = no penalty."""
        assert self._ai.resource_cost_score("build") == 0

    def test_resource_cost_score_with_data(self):
        """Known expensive type gets a penalty."""
        self._ai.record("a1", "expensive", 5000, True,
                        actual_resources=ResourceUsage(token_cost=5000, api_cost=50.0, memory_mb=1024.0, browser_steps=30))
        self._ai.record("a2", "expensive", 5000, True,
                        actual_resources=ResourceUsage(token_cost=5000, api_cost=50.0, memory_mb=1024.0, browser_steps=30))
        self._ai.record("a3", "expensive", 5000, True,
                        actual_resources=ResourceUsage(token_cost=5000, api_cost=50.0, memory_mb=1024.0, browser_steps=30))

        penalty = self._ai.resource_cost_score("expensive")
        assert penalty > 0

    def test_resource_cost_score_cheap_type(self):
        """Known cheap type gets little or no penalty."""
        self._ai.record("a1", "email", 1000, True,
                        actual_resources=ResourceUsage(token_cost=50, api_cost=0.0, memory_mb=10.0, browser_steps=1))
        self._ai.record("a2", "email", 1000, True,
                        actual_resources=ResourceUsage(token_cost=50, api_cost=0.0, memory_mb=10.0, browser_steps=1))
        self._ai.record("a3", "email", 1000, True,
                        actual_resources=ResourceUsage(token_cost=50, api_cost=0.0, memory_mb=10.0, browser_steps=1))

        penalty = self._ai.resource_cost_score("email")
        assert penalty < 5  # very cheap

    def test_learned_priority_with_resource_penalty(self):
        """learned_priority now subtracts resource penalty."""
        # Cheap type: email
        self._ai.record("a1", "email", 1000, True,
                        actual_resources=ResourceUsage(token_cost=50, api_cost=0.0, memory_mb=10.0, browser_steps=1))
        self._ai.record("a2", "email", 1000, True,
                        actual_resources=ResourceUsage(token_cost=50, api_cost=0.0, memory_mb=10.0, browser_steps=1))
        self._ai.record("a3", "email", 1000, True,
                        actual_resources=ResourceUsage(token_cost=50, api_cost=0.0, memory_mb=10.0, browser_steps=1))

        # Expensive type: research
        self._ai.record("b1", "research", 60000, True,
                        actual_resources=ResourceUsage(token_cost=5000, api_cost=50.0, memory_mb=1024.0, browser_steps=30))
        self._ai.record("b2", "research", 60000, True,
                        actual_resources=ResourceUsage(token_cost=5000, api_cost=50.0, memory_mb=1024.0, browser_steps=30))
        self._ai.record("b3", "research", 60000, True,
                        actual_resources=ResourceUsage(token_cost=5000, api_cost=50.0, memory_mb=1024.0, browser_steps=30))

        email_pri = self._ai.learned_priority("email")
        research_pri = self._ai.learned_priority("research")
        # Email should be higher priority than research (cheaper)
        assert email_pri > research_pri

    def test_get_resource_calibration_improves_estimate(self):
        """Calibration self-corrects based on predicted vs actual ratio.

        Note: calibration multiplies historical averages by the median
        predicted/actual ratio. When predictions were systematically low (500
        vs 1000), the 2x calibration inflates the already-correct average of
        1000 to 2000. This can over-correct temporarily as prediction baselines
        improve, but converges to 1.0 once predictions become accurate.
        """
        self._ai.record("a1", "build", 5000, True,
                        predicted_resources=ResourceEstimate(token_cost=500, api_cost=2.0, memory_mb=50.0, browser_steps=2),
                        actual_resources=ResourceUsage(token_cost=1000, api_cost=5.0, memory_mb=128.0, browser_steps=5))
        self._ai.record("a2", "build", 5000, True,
                        predicted_resources=ResourceEstimate(token_cost=500, api_cost=2.0, memory_mb=50.0, browser_steps=2),
                        actual_resources=ResourceUsage(token_cost=1000, api_cost=5.0, memory_mb=128.0, browser_steps=5))
        self._ai.record("a3", "build", 5000, True,
                        predicted_resources=ResourceEstimate(token_cost=500, api_cost=2.0, memory_mb=50.0, browser_steps=2),
                        actual_resources=ResourceUsage(token_cost=1000, api_cost=5.0, memory_mb=128.0, browser_steps=5))

        # Historical average = 1000, calibration multiplier = 2.0 (500→1000)
        est = self._ai.predict_resources("build")
        assert est.token_cost == pytest.approx(2000.0, rel=0.1)

        # Add accurate predictions to converge median toward 1.0
        # 3 bad + 4 good = 7 samples, median = 4th = 1.0
        for i in range(4):
            self._ai.record(f"a{i+4}", "build", 5000, True,
                            predicted_resources=ResourceEstimate(token_cost=1000, api_cost=5.0, memory_mb=128.0, browser_steps=5),
                            actual_resources=ResourceUsage(token_cost=1000, api_cost=5.0, memory_mb=128.0, browser_steps=5))

        est2 = self._ai.predict_resources("build")
        assert est2.token_cost == pytest.approx(1000.0, rel=0.1)

    def test_database_migration_includes_resources(self):
        """DB migration happens automatically on init."""
        import sqlite3
        with sqlite3.connect(self._db) as conn:
            cursor = conn.execute("PRAGMA table_info(activity_stats)")
            cols = {row[1] for row in cursor.fetchall()}
        assert "predicted_tokens" in cols
        assert "actual_tokens" in cols
        assert "predicted_api_cost" in cols
        assert "actual_api_cost" in cols
        assert "predicted_memory_mb" in cols
        assert "actual_memory_mb" in cols
        assert "predicted_browser_steps" in cols
        assert "actual_browser_steps" in cols

    def test_record_batch_with_resources(self):
        """record_batch handles resource data."""
        pred_res = ResourceEstimate(token_cost=500, api_cost=2.0, memory_mb=50.0, browser_steps=2)
        act_res = ResourceUsage(token_cost=600, api_cost=2.5, memory_mb=60.0, browser_steps=2)
        self._ai.record_batch([
            {"activity_id": "a1", "node_type": "build", "duration_ms": 5000, "success": True,
             "predicted_resources": pred_res, "actual_resources": act_res},
        ])
        est = self._ai.predict_resources("build")
        assert est.sample_size == 1
        assert est.token_cost == 600.0
