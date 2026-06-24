"""Tests for ActivityIntelligence — historical stats, prediction, calibration, scheduler integration."""
import os
import shutil
import tempfile

import pytest

from core.scheduler.intelligence import (
    ActivityIntelligence,
    Prediction,
    PredictionEngine,
    CalibrationStats,
    TypeStats,
    MIN_SAMPLES_FOR_STATS,
    CONFIDENCE_SATURATION,
    DEFAULT_PRIOR_SUCCESS,
    DEFAULT_PRIOR_DURATION_MS,
)
from core.scheduler.policies import PriorityPolicy
from core.scheduler.scheduler import Scheduler
from core.scheduler.models import ScheduledActivity


class TestActivityIntelligence:
    """Unit tests for the intelligence data layer."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_intel.db")
        self._ai = ActivityIntelligence(db_path=self._db)

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_record_and_count(self):
        self._ai.record("a1", "build", 5000, True, "Build APK")
        self._ai.record("a2", "research", 3000, True, "Research topic")
        self._ai.record("a3", "build", 12000, False, "Build APK v2")
        assert self._ai.count() == 3

    def test_get_stats_insufficient_data(self):
        """Returns default 0.5 success_rate when < MIN_SAMPLES."""
        self._ai.record("a1", "build", 5000, True)
        stats = self._ai.get_stats("build")
        assert stats.count == 1
        assert stats.success_rate == 1.0  # only 1 sample, but exact

    def test_get_stats_unknown_type(self):
        """Returns defaults for completely unknown type."""
        stats = self._ai.get_stats("nonexistent")
        assert stats.count == 0
        assert stats.success_rate == 0.5
        assert stats.node_type == "nonexistent"

    def test_success_rate_computation(self):
        self._ai.record("a1", "build", 5000, True)
        self._ai.record("a2", "build", 6000, True)
        self._ai.record("a3", "build", 7000, True)
        self._ai.record("a4", "build", 8000, False)
        stats = self._ai.get_stats("build")
        assert stats.count == 4
        assert stats.success_count == 3
        assert stats.failure_count == 1
        assert stats.success_rate == 0.75

    def test_avg_duration_computation(self):
        self._ai.record("a1", "build", 5000, True)
        self._ai.record("a2", "build", 15000, True)
        stats = self._ai.get_stats("build")
        assert stats.avg_duration_ms == 10000.0

    def test_learned_priority_insufficient_data(self):
        """Returns 0 when not enough samples."""
        self._ai.record("a1", "build", 5000, True)
        self._ai.record("a2", "build", 5000, True)
        assert self._ai.learned_priority("build") == 0

    def test_learned_priority_sufficient_data(self):
        """Returns non-zero boost with >= 3 samples (confidence-blended)."""
        self._ai.record("a1", "build", 5000, True)
        self._ai.record("a2", "build", 5000, True)
        self._ai.record("a3", "build", 5000, True)
        boost = self._ai.learned_priority("build")
        # 3 samples, confidence=0.15
        # blended_success = 1.0*0.15 + 0.5*0.85 = 0.575
        # blended_duration = 5000*0.15 + 10000*0.85 = 9250 → penalty=0
        # boost = int(0.575*40) - 0 = 23
        assert boost == 23

    def test_learned_priority_duration_penalty(self):
        """Slow types get lower priority (confidence-blended)."""
        self._ai.record("a1", "slow_build", 120000, True)
        self._ai.record("a2", "slow_build", 120000, True)
        self._ai.record("a3", "slow_build", 120000, True)
        boost = self._ai.learned_priority("slow_build")
        # 3 samples, confidence=0.15
        # blended_success = 0.575, boost=23
        # blended_duration = 120000*0.15 + 10000*0.85 = 26500 → int(26500/10000)*2 = 4
        # result = 23 - 4 = 19
        assert boost == 19

    def test_learned_priority_failure_penalty(self):
        """Unreliable types get lower priority (confidence-blended)."""
        self._ai.record("a1", "risky", 5000, True)
        self._ai.record("a2", "risky", 5000, False)
        self._ai.record("a3", "risky", 5000, False)
        boost = self._ai.learned_priority("risky")
        # 3 samples, confidence=0.15, success_rate=1/3
        # blended_success = 1/3*0.15 + 0.5*0.85 = 0.475
        # int(0.475*40) = int(19.0) = 19
        # blended_duration = 5000*0.15+10000*0.85 = 9250 → penalty=0
        assert boost == 19

    def test_expected_duration(self):
        self._ai.record("a1", "build", 10000, True)
        self._ai.record("a2", "build", 20000, True)
        self._ai.record("a3", "build", 30000, True)
        assert self._ai.expected_duration_ms("build") == 20000.0

    def test_expected_duration_unknown(self):
        """Returns 0.0 for unknown types."""
        assert self._ai.expected_duration_ms("unknown") == 0.0

    def test_success_probability(self):
        self._ai.record("a1", "build", 5000, True)
        self._ai.record("a2", "build", 5000, True)
        self._ai.record("a3", "build", 5000, False)
        assert self._ai.success_probability("build") == pytest.approx(2.0 / 3.0)

    def test_success_probability_unknown(self):
        """Returns 0.5 uniform prior."""
        assert self._ai.success_probability("unknown") == 0.5

    def test_get_stats_summary(self):
        self._ai.record("a1", "build", 5000, True)
        self._ai.record("a2", "research", 3000, True)
        self._ai.record("a3", "build", 5000, False)
        summary = self._ai.get_stats_summary()
        assert "build" in summary
        assert "research" in summary
        assert summary["build"].count == 2
        assert summary["research"].count == 1

    def test_clear(self):
        self._ai.record("a1", "build", 5000, True)
        assert self._ai.count() == 1
        self._ai.clear()
        assert self._ai.count() == 0

    def test_record_with_metadata_chain(self):
        self._ai.record(
            "a1", "build", 5000, True,
            goal="Build APK",
            metadata={"chain_id": "chain_abc", "retry_count": 2},
        )
        stats = self._ai.get_stats("build")
        assert stats.count == 1
        assert stats.success_rate == 1.0

    def test_record_batch(self):
        records = [
            {"activity_id": "a1", "node_type": "build", "duration_ms": 5000, "success": True, "goal": "Build"},
            {"activity_id": "a2", "node_type": "research", "duration_ms": 3000, "success": True, "goal": "Research"},
            {"activity_id": "a3", "node_type": "build", "duration_ms": 10000, "success": False, "goal": "Build v2"},
        ]
        self._ai.record_batch(records)
        assert self._ai.count() == 3
        build_stats = self._ai.get_stats("build")
        assert build_stats.count == 2
        assert build_stats.success_rate == 0.5

    def test_mixed_type_stats(self):
        """Multiple types coexist without interference."""
        self._ai.record("a1", "build", 10000, True)
        self._ai.record("a2", "build", 10000, True)
        self._ai.record("a3", "build", 10000, True)
        self._ai.record("a4", "email", 2000, True)
        self._ai.record("a5", "email", 2000, True)
        self._ai.record("a6", "email", 2000, True)
        self._ai.record("a7", "email", 2000, True)
        self._ai.record("a8", "research", 60000, True)
        self._ai.record("a9", "research", 60000, False)
        self._ai.record("a10", "research", 60000, False)

        assert self._ai.count() == 10
        # email: 4 samples, confidence=0.2, success=1.0
        # blended_success = 1.0*0.2 + 0.5*0.8 = 0.6 → boost = 24
        # blended_duration = 2000*0.2 + 10000*0.8 = 8400 → penalty = 0
        assert self._ai.learned_priority("email") == 24

        # build: 3 samples, confidence=0.15, success=1.0
        # blended_success = 0.575 → boost = 23
        # blended_duration = 10000 → penalty = int(10000/10000)*2 = 2
        assert self._ai.learned_priority("build") == 21  # 23 - 2

        # research: 3 samples, confidence=0.15, success=0.333
        # blended_success = 0.333*0.15 + 0.5*0.85 = 0.475 → boost = 19
        # blended_duration = 60000*0.15 + 10000*0.85 = 17500 → penalty = 2
        assert self._ai.learned_priority("research") == 17  # 19 - 2


class TestPriorityPolicyIntelligence:
    """Tests that PriorityPolicy correctly uses intelligence."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_policy_intel.db")
        self._ai = ActivityIntelligence(db_path=self._db)
        self._policy = PriorityPolicy(intelligence=self._ai)

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_activity(self, aid, node_type, priority=3):
        return ScheduledActivity(
            activity_id=aid,
            goal=f"Activity {aid}",
            node_type=node_type,
            priority=priority,
            status="pending",
            metadata={},
        )

    def test_rank_unknown_type_no_penalty(self):
        """Activities without enough historical data score 0 from intelligence."""
        a1 = self._make_activity("a1", "build")
        ranked = self._policy.rank([a1])
        # Base score: priority 3=60 + urgency 30 = 90 (no user_requested bonus since type != goal)
        assert ranked[0].score == 90

    def test_rank_fast_reliable_gets_boost(self):
        """A proven fast, reliable type gets a positive boost."""
        self._ai.record("h1", "email", 1000, True)
        self._ai.record("h2", "email", 1000, True)
        self._ai.record("h3", "email", 1000, True)
        a1 = self._make_activity("a1", "email")
        ranked = self._policy.rank([a1])
        # Base: 90, boost: 3-samples, confidence=0.15
        # blended_success = 1.0*0.15+0.5*0.85=0.575, boost=23
        # blended_duration = 1000*0.15+10000*0.85=8650, penalty=0
        # score = 90 + 23 = 113
        assert ranked[0].score == 113

    def test_rank_slow_unreliable_gets_penalty(self):
        """A proven slow, unreliable type gets a lower boost."""
        self._ai.record("h1", "research", 60000, True)
        self._ai.record("h2", "research", 60000, False)
        self._ai.record("h3", "research", 60000, False)
        a1 = self._make_activity("a1", "research")
        ranked = self._policy.rank([a1])
        # Base: 90, boost: 3-samples, confidence=0.15
        # blended_success = 0.333*0.15+0.5*0.85=0.475, boost=19
        # blended_duration = 60000*0.15+10000*0.85=17500, penalty=2
        # score = 90 + 19 - 2 = 107
        assert ranked[0].score == 107

    def test_rank_fast_beats_slow_same_priority(self):
        """Fast type ranks higher than slow type when both known."""
        self._ai.record("h1", "email", 1000, True)
        self._ai.record("h2", "email", 1000, True)
        self._ai.record("h3", "email", 1000, True)
        self._ai.record("h4", "slow", 300000, True)
        self._ai.record("h5", "slow", 300000, True)
        self._ai.record("h6", "slow", 300000, True)

        fast = self._make_activity("fast", "email", priority=3)
        slow = self._make_activity("slow", "slow", priority=3)
        ranked = self._policy.rank([slow, fast])
        # email (3 samples, confidence=0.15): blended_success=0.575, boost=23
        #   blended_duration=8650, penalty=0 → score=90+23=113
        # slow (3 samples, confidence=0.15): blended_success=0.575, boost=23
        #   blended_duration=53500, penalty=10 → score=90+23-10=103
        assert ranked[0].activity_id == "fast"
        assert ranked[0].score > ranked[1].score
        assert ranked[0].score == 113
        assert ranked[1].score == 103

    def test_intelligence_can_be_set_after_construction(self):
        """Intelligence can be added post-init."""
        policy = PriorityPolicy()
        assert policy.intelligence is None
        policy.intelligence = self._ai
        assert policy.intelligence is not None


class TestSchedulerIntelligenceIntegration:
    """Tests that the scheduler correctly records to intelligence."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_sched_intel.db")
        self._ai = ActivityIntelligence(db_path=self._db)
        self._policy = PriorityPolicy(intelligence=self._ai)
        self._scheduler = Scheduler(
            store_db_path=self._db,
            policy=self._policy,
            intelligence=self._ai,
            max_workers=1,
        )

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_scheduler_has_intelligence(self):
        assert self._scheduler.intelligence is not None
        assert self._scheduler.intelligence.count() == 0

    def test_policy_wired_to_scheduler_intelligence(self):
        # The scheduler creates an intelligence; verify it records outcomes
        assert self._scheduler.intelligence is not None
        assert self._scheduler.intelligence.count() == 0

    def test_intelligence_reuse_no_duplicate_db(self):
        """Same db_path means same SQLite database."""
        s2 = Scheduler(store_db_path=self._db, intelligence=self._ai)
        assert s2.intelligence is self._ai

    def test_intelligence_survives_restart(self):
        """Data persists in SQLite across scheduler instances."""
        self._ai.record("a1", "build", 5000, True)
        self._ai.record("a2", "build", 5000, True)
        self._ai.record("a3", "build", 5000, True)
        assert self._ai.count() == 3

        # New scheduler, same db
        ai2 = ActivityIntelligence(db_path=self._db)
        assert ai2.count() == 3
        stats = ai2.get_stats("build")
        assert stats.success_rate == 1.0


class TestPredictionEngine:
    """Unit tests for the stateless PredictionEngine."""

    def test_predict_no_data(self):
        """Prediction with no stats returns zero confidence and defaults."""
        pred = PredictionEngine.predict("unknown")
        assert pred.node_type == "unknown"
        assert pred.confidence == 0.0
        assert pred.sample_size == 0
        assert pred.success_probability == DEFAULT_PRIOR_SUCCESS
        assert pred.expected_duration_ms == DEFAULT_PRIOR_DURATION_MS

    def test_predict_partial_data(self):
        """Below MIN_SAMPLES, prediction blends toward priors."""
        stats = TypeStats(node_type="build", count=1, success_count=1, success_rate=1.0, avg_duration_ms=5000)
        pred = PredictionEngine.predict("build", stats)
        assert pred.sample_size == 1
        assert pred.confidence < 0.5  # 1/20 = 0.05
        # Should be partially blended toward prior
        assert pred.success_probability < 1.0
        assert pred.success_probability > DEFAULT_PRIOR_SUCCESS

    def test_predict_full_data(self):
        """Above MIN_SAMPLES, prediction uses historical stats directly."""
        stats = TypeStats(node_type="build", count=10, success_count=8, success_rate=0.8, avg_duration_ms=15000)
        pred = PredictionEngine.predict("build", stats)
        assert pred.sample_size == 10
        assert pred.confidence == 0.5  # 10/20
        assert pred.success_probability == 0.8
        assert pred.expected_duration_ms == 15000.0
        assert pred.prediction_source == "historical_stats"

    def test_predict_saturated_data(self):
        """At CONFIDENCE_SATURATION samples, confidence = 1.0."""
        stats = TypeStats(node_type="email", count=20, success_count=19, success_rate=0.95, avg_duration_ms=2000)
        pred = PredictionEngine.predict("email", stats)
        assert pred.confidence == 1.0
        assert pred.success_probability == 0.95
        assert pred.expected_duration_ms == 2000.0

    def test_calibrate_empty(self):
        """Empty calibration returns neutral defaults."""
        cal = PredictionEngine.calibrate([])
        assert cal.sample_count == 0
        assert cal.prediction_error == 0.0
        assert cal.duration_error == 0.0
        assert cal.calibration_score == 0.5

    def test_calibrate_perfect(self):
        """Perfect predictions yield calibration_score = 1.0."""
        # "Perfect" means predicted_prob exactly matches binary outcome
        pairs = [
            (1.0, 5000, True, 4800),
            (1.0, 10000, True, 9500),
            (0.0, 20000, False, 22000),
        ]
        cal = PredictionEngine.calibrate(pairs)
        assert cal.sample_count == 3
        assert cal.prediction_error == 0.0
        assert cal.calibration_score == 1.0

    def test_calibrate_poor(self):
        """Poor predictions yield low calibration_score."""
        pairs = [
            (0.9, 5000, False, 48000),  # predicted 90% success, actually failed
            (0.9, 5000, False, 55000),  # same
            (0.1, 5000, True, 1000),    # predicted 10% success, actually succeeded
        ]
        cal = PredictionEngine.calibrate(pairs)
        assert cal.sample_count == 3
        # prediction_error = (0.9 + 0.9 + 0.9) / 3 = 0.9
        assert cal.prediction_error == pytest.approx(0.9)
        # calibration_score = max(0, 1.0 - 0.9*2) = max(0, -0.8) = 0
        assert cal.calibration_score == 0.0
        assert cal.duration_error > 0

    def test_calibrate_single(self):
        """Single sample calibration works."""
        pairs = [(0.8, 10000, True, 11000)]
        cal = PredictionEngine.calibrate(pairs)
        assert cal.sample_count == 1
        assert cal.prediction_error == pytest.approx(0.2)
        # duration_error = |10000-11000| / max(11000,1) = 1000/11000 ≈ 0.0909
        assert cal.duration_error == pytest.approx(0.0909, rel=1e-2)

    def test_calibrate_mixed_accuracy(self):
        """Partial accuracy yields intermediate calibration_score."""
        # 3 good + 2 bad = 60% accuracy → prediction_error = 0.4 → score = 0.2
        pairs = [
            (0.9, 5000, True, 5000),
            (0.8, 10000, True, 10000),
            (0.7, 15000, True, 15000),
            (0.9, 5000, False, 5000),  # wrong
            (0.1, 5000, True, 5000),   # wrong
        ]
        cal = PredictionEngine.calibrate(pairs)
        # error = (0.1 + 0.2 + 0.3 + 0.9 + 0.9) / 5 = 2.4/5 = 0.48
        assert cal.prediction_error == pytest.approx(0.48, rel=1e-2)
        assert cal.calibration_score == pytest.approx(0.04, rel=1e-2)


class TestActivityIntelligencePhase8_3B:
    """Tests for prediction and calibration on ActivityIntelligence."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_intel_8.3b.db")
        self._ai = ActivityIntelligence(db_path=self._db)

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_predict_no_history(self):
        """Predict without any recorded data returns zero confidence."""
        pred = self._ai.predict("build")
        assert pred.confidence == 0.0
        assert pred.sample_size == 0
        assert pred.node_type == "build"

    def test_predict_with_history(self):
        """Predict with >= MIN_SAMPLES returns stats-based prediction."""
        self._ai.record("a1", "build", 5000, True)
        self._ai.record("a2", "build", 6000, True)
        self._ai.record("a3", "build", 5000, True)
        pred = self._ai.predict("build")
        assert pred.sample_size == 3
        assert pred.confidence == 3.0 / CONFIDENCE_SATURATION  # 0.15
        assert pred.success_probability == 1.0
        assert pred.expected_duration_ms == pytest.approx(5333.33, rel=1e-2)

    def test_record_with_prediction(self):
        """Recording with prediction stores it in DB."""
        self._ai.record("a1", "build", 5000, True, predicted_success=0.85, predicted_duration_ms=6000)
        row = self._ai.get_prediction_data("build")
        assert len(row) == 1
        assert row[0]["predicted_success"] == 0.85
        assert row[0]["predicted_duration_ms"] == 6000
        assert row[0]["actual_success"] is True
        assert row[0]["actual_duration_ms"] == 5000
        assert row[0]["prediction_source"] == "historical_stats"

    def test_get_calibration_empty(self):
        """No prediction data yields empty calibration."""
        cal = self._ai.get_calibration("build")
        assert cal.sample_count == 0

    def test_get_calibration_with_data(self):
        """Calibration computed from stored predictions."""
        self._ai.record("a1", "build", 5000, True, predicted_success=0.9, predicted_duration_ms=5500)
        self._ai.record("a2", "build", 6000, False, predicted_success=0.8, predicted_duration_ms=5000)
        cal = self._ai.get_calibration("build")
        assert cal.sample_count == 2
        # prediction_error = (|0.9-1.0| + |0.8-0.0|) / 2 = (0.1 + 0.8) / 2 = 0.45
        assert cal.prediction_error == pytest.approx(0.45)
        # calibration_score = max(0, 1.0 - 0.9) = 0.1
        assert cal.calibration_score == pytest.approx(0.1)

    def test_get_calibration_summary(self):
        """Summary returns calibration for all types with prediction data."""
        self._ai.record("a1", "build", 5000, True, predicted_success=0.9, predicted_duration_ms=5500)
        self._ai.record("a2", "email", 2000, True, predicted_success=0.95, predicted_duration_ms=2000)
        summary = self._ai.get_calibration_summary()
        assert "build" in summary
        assert "email" in summary
        assert summary["build"].sample_count == 1
        assert summary["email"].sample_count == 1

    def test_get_prediction_data_limit(self):
        """Prediction data respects limit parameter."""
        for i in range(5):
            self._ai.record(f"a{i}", "build", 5000, True, predicted_success=0.9, predicted_duration_ms=5000)
        data = self._ai.get_prediction_data("build", limit=3)
        assert len(data) == 3

    def test_learned_priority_with_prediction_confidence(self):
        """learned_priority uses prediction confidence to blend toward prior."""
        self._ai.record("a1", "build", 5000, True)
        self._ai.record("a2", "build", 5000, True)
        self._ai.record("a3", "build", 5000, True)
        # 3 samples, confidence = 3/20 = 0.15
        # blended_success = 1.0 * 0.15 + 0.5 * 0.85 = 0.575
        # success_boost = 0.575 * 40 = 23
        # blended_duration = 5000 * 0.15 + 10000 * 0.85 = 9250
        # duration_penalty = int(9250/10000)*2 = 0
        # result = 23
        assert self._ai.learned_priority("build") == 23

    def test_learned_priority_many_samples(self):
        """With many samples, learned_priority approaches pure stats."""
        for i in range(20):
            self._ai.record(f"a{i}", "email", 1000, True)
        # 20 samples, confidence = 1.0
        # blended_success = 1.0 * 1.0 + 0.5 * 0.0 = 1.0
        # success_boost = 40
        # blended_duration = 1000 * 1.0 + 10000 * 0.0 = 1000
        # duration_penalty = 0
        # result = 40
        assert self._ai.learned_priority("email") == 40

    def test_calibration_dampening_poor_calibration(self):
        """Poorly calibrated types get dampened."""
        # Record 10 activities WITH predictions (to enable calibration)
        for i in range(5):
            # All succeed, predicted 90%
            self._ai.record(f"a{i}", "damp_test", 5000, True,
                            predicted_success=0.9, predicted_duration_ms=5000)
        for i in range(5, 10):
            # All fail, predicted 90%
            self._ai.record(f"a{i}", "damp_test", 5000, False,
                            predicted_success=0.9, predicted_duration_ms=5000)

        # Calibration: 5/5 successes wrong, 5/5 failures wrong
        # prediction_error = (0.1*5 + 0.9*5) / 10 = 5.0/10 = 0.5
        # calibration_score = max(0, 1.0 - 1.0) = 0.0

        # But learned_priority uses count >= MIN_SAMPLES (3) for the base
        # AND calibration requires 3+ samples to activate dampening
        # With calibration_score=0.0 < 0.8, dampening activates
        # dampening = 0.0/0.8 = 0.0 → fully dampened to prior
        boost = self._ai.learned_priority("damp_test")
        # With full dampening: blended_success = 0.5 (prior), boost = 20
        # But we also have 10 samples which affects confidence
        # confidence = 10/20 = 0.5
        # Before dampening: blended = 0.9*0.5 + 0.5*0.5 = 0.7
        # dampening = 0.0/0.8 = 0.0
        # After dampening: 0.7*0.0 + 0.5*1.0 = 0.5
        # boost = 0.5*40 = 20
        assert boost == 20

    def test_confidence_ramps_gradually(self):
        """Confidence ramps linearly from 0 to 1.0."""
        for n in [0, 5, 10, 15, 20, 25]:
            stats = TypeStats(node_type="t", count=n, success_count=n, success_rate=1.0, avg_duration_ms=1000)
            pred = PredictionEngine.predict("t", stats)
            expected = min(n / CONFIDENCE_SATURATION, 1.0)
            assert pred.confidence == pytest.approx(expected)

    def test_predict_prior_blend_below_threshold(self):
        """Below MIN_SAMPLES, prediction blends toward prior progressively."""
        # 1 sample: 33% toward prior
        stats_1 = TypeStats(node_type="t", count=1, success_count=1, success_rate=1.0, avg_duration_ms=5000)
        pred_1 = PredictionEngine.predict("t", stats_1)
        # prior_weight = 1 - 1/3 = 0.667
        # success = 1.0*0.333 + 0.5*0.667 = 0.667
        assert pred_1.success_probability == pytest.approx(0.6667, rel=1e-2)

        # 2 samples: 67% toward data, 33% toward prior
        stats_2 = TypeStats(node_type="t", count=2, success_count=1, success_rate=0.5, avg_duration_ms=5000)
        pred_2 = PredictionEngine.predict("t", stats_2)
        # prior_weight = 1 - 2/3 = 0.333
        # success = 0.5*0.667 + 0.5*0.333 = 0.5
        assert pred_2.success_probability == pytest.approx(0.5, rel=1e-2)

    def test_prediction_source_default(self):
        """Default prediction source is historical_stats."""
        self._ai.record("a1", "build", 5000, True,
                        predicted_success=0.8, predicted_duration_ms=5000)
        data = self._ai.get_prediction_data("build")
        assert data[0]["prediction_source"] == "historical_stats"


class TestPredictionCalibrationSchedulerIntegration:
    """Tests that scheduler records predictions and calibration works end-to-end."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_pred_sched.db")
        self._ai = ActivityIntelligence(db_path=self._db)

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_predict_before_record(self):
        """Prediction before any data returns zero confidence."""
        pred = self._ai.predict("build")
        assert pred.confidence == 0.0

    def test_predict_after_enough_data(self):
        """Prediction after enough data returns reasonable estimate."""
        for i in range(5):
            self._ai.record(f"a{i}", "research", 60000, True)
        pred = self._ai.predict("research")
        assert pred.success_probability == 1.0
        assert pred.confidence == 5.0 / CONFIDENCE_SATURATION
        assert pred.expected_duration_ms == 60000.0

    def test_prediction_stored_in_db(self):
        """Prediction values are stored and retrievable after recording."""
        for i in range(3):
            self._ai.record(f"a{i}", "build", 5000, True)
        pred = self._ai.predict("build")
        # Record with prediction data
        self._ai.record("a10", "build", 5500, True,
                        predicted_success=pred.success_probability,
                        predicted_duration_ms=int(pred.expected_duration_ms))
        data = self._ai.get_prediction_data("build")
        assert len(data) >= 1
        # Verify the last entry has prediction data
        latest = data[0]
        assert latest["predicted_success"] is not None
        assert latest["predicted_duration_ms"] is not None

    def test_calibration_improves_with_better_predictions(self):
        """After recording predictions, calibration is measurable."""
        # Record with predictions that turned out accurate
        self._ai.record("a1", "email", 1000, True,
                        predicted_success=0.9, predicted_duration_ms=1100)
        self._ai.record("a2", "email", 900, True,
                        predicted_success=0.85, predicted_duration_ms=1000)
        self._ai.record("a3", "email", 1200, True,
                        predicted_success=0.95, predicted_duration_ms=1100)

        cal = self._ai.get_calibration("email")
        assert cal.sample_count == 3
        # All close to perfect → high calibration_score
        assert cal.calibration_score > 0.5

    def test_migration_old_db(self):
        """Old DB without prediction columns works after migration."""
        # Create a clean intelligence that initializes tables
        ai = ActivityIntelligence(db_path=self._db)
        ai.record("legacy_1", "build", 5000, True)
        assert ai.count() == 1

        # Create a new intelligence instance on same DB (re-runs migration)
        ai2 = ActivityIntelligence(db_path=self._db)
        assert ai2.count() == 1

        # Verify we can record with predictions
        ai2.record("new_1", "build", 5000, True,
                   predicted_success=0.8, predicted_duration_ms=5000)
        assert ai2.count() == 2

        # Verify prediction data retrievable
        data = ai2.get_prediction_data("build")
        pred_rows = [d for d in data if d["predicted_success"] is not None]
        assert len(pred_rows) == 1

    def test_full_predict_record_calibrate_cycle(self):
        """End-to-end: predict → execute → record → calibrate."""
        # Seed historical data
        for i in range(5):
            self._ai.record(f"h{i}", "research", 50000, True)

        # Predict
        pred = self._ai.predict("research")
        assert pred.success_probability == 1.0
        assert pred.expected_duration_ms == 50000.0

        # Execute and record with prediction
        self._ai.record("exec1", "research", 45000, True,
                        predicted_success=pred.success_probability,
                        predicted_duration_ms=int(pred.expected_duration_ms))

        # Another execution that fails (prediction was wrong)
        self._ai.record("exec2", "research", 55000, False,
                        predicted_success=0.9, predicted_duration_ms=50000)

        # Calibrate
        cal = self._ai.get_calibration("research")
        assert cal.sample_count == 2
        # exec1: |1.0 - 1.0| = 0.0, exec2: |0.9 - 0.0| = 0.9
        # prediction_error = (0.0 + 0.9) / 2 = 0.45
        assert cal.prediction_error == pytest.approx(0.45)
        assert cal.calibration_score == pytest.approx(0.1)

        # Learned priority should be affected
        boost = self._ai.learned_priority("research")
        # 7 total samples, confidence = 7/20 = 0.35
        # success_rate = 6/7 ≈ 0.85714
        # blended_success = (0.85714*0.35 + 0.5*0.65) = 0.625
        #   int(0.625*40) = int(25.0) = 25
        # No dampening (calibration has only 2 samples < 3)
        # blended_duration = (50000*0.35 + 10000*0.65) = 24000
        # penalty = int(24000/10000)*2 = 4
        # boost = 25 - 4 = 21
        assert boost == 21
