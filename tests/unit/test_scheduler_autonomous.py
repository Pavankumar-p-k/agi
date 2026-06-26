"""Tests for Phase 8.4 — AutonomousScheduler bridge."""
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from core.scheduler.autonomous import AutonomousScheduler, OpportunityActivity
from core.scheduler.decision import DecisionEngine, DecisionEstimate
from core.scheduler.intelligence import ActivityIntelligence
from core.scheduler.models import ScheduledActivity
from core.scheduler.policies import DecisionPriorityPolicy


class TestOpportunityActivity:
    """OpportunityActivity dataclass."""

    def test_defaults(self):
        oa = OpportunityActivity(
            opportunity_id="opp_1",
            target_system="browser_automation",
            description="Improve success rate",
            source="bottleneck",
            source_score=0.6,
            decision_ev=0.5,
            decision_confidence=0.7,
            decision_risk=0.2,
        )
        assert oa.opportunity_id == "opp_1"
        assert oa.activity_id == ""
        assert oa.submitted is False

    def test_submitted_flag(self):
        oa = OpportunityActivity(
            opportunity_id="opp_1",
            target_system="test",
            description="test",
            source="ceiling",
            source_score=0.5,
            decision_ev=0.5,
            decision_confidence=0.7,
            decision_risk=0.2,
        )
        oa.submitted = True
        oa.activity_id = "act_1"
        assert oa.submitted
        assert oa.activity_id == "act_1"


class TestAutonomousScheduler:
    """AutonomousScheduler bridge — discover, evaluate, submit."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_auto.db")

        self._ai = ActivityIntelligence(db_path=self._db)
        self._engine = DecisionEngine(intelligence=self._ai)
        self._queue = MagicMock()
        self._scheduler = AutonomousScheduler(
            engine=None,  # will be set per test
            decision=self._engine,
            queue=self._queue,
        )

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_mock_opp(self, opp_id="opp_1", target="browser_automation",
                       description="Improve browser success rate",
                       source="bottleneck", score=0.6,
                       success_prob=0.7, confidence=0.5):
        opp = MagicMock()
        opp.id = opp_id
        opp.target_system = target
        opp.improvement_description = description
        opp.source = MagicMock()
        opp.source.value = source
        opp.opportunity_score = score
        opp.success_probability = success_prob
        opp.confidence = confidence
        opp.status = MagicMock()
        opp.status.value = "open"
        return opp

    def test_run_cycle_no_engine(self):
        """Without an engine, cycle returns zero discovered."""
        result = self._scheduler.run_cycle()
        assert result["discovered"] == 0
        assert result["submitted"] == 0
        assert result["rejected"] == 0

    def test_run_cycle_discovery_failure(self):
        """Engine failure is caught gracefully."""
        engine = MagicMock()
        engine.discover_all.side_effect = Exception("discovery error")
        self._scheduler._engine = engine

        result = self._scheduler.run_cycle()
        assert result["discovered"] == 0

    def test_run_cycle_submits_valid_opportunity(self):
        """A high-scoring opportunity passes all gates and is submitted."""
        engine = MagicMock()
        opp = self._make_mock_opp(score=0.8, confidence=0.9, success_prob=0.9)
        engine.discover_all.return_value = [opp]
        self._scheduler._engine = engine

        # Queue returns a valid ScheduledActivity
        self._queue.submit.return_value = ScheduledActivity(
            activity_id="opp_opp_1",
            node_type="opportunity",
        )

        result = self._scheduler.run_cycle()
        assert result["discovered"] == 1
        assert result["submitted"] == 1
        assert result["rejected"] == 0
        self._queue.submit.assert_called_once()

    def test_run_cycle_rejects_low_ev(self):
        """Low expected_value is rejected."""
        engine = MagicMock()
        opp = self._make_mock_opp(score=0.01, confidence=0.9, success_prob=0.9)
        engine.discover_all.return_value = [opp]
        self._scheduler._engine = engine

        result = self._scheduler.run_cycle()
        assert result["discovered"] == 1
        assert result["submitted"] == 0
        assert result["rejected"] == 1
        assert "EV" in result["rejected_reasons"][0]["reason"]

    def test_run_cycle_rejects_low_confidence(self):
        """Low confidence is rejected."""
        engine = MagicMock()
        opp = self._make_mock_opp(score=0.6, confidence=0.01, success_prob=0.9)
        engine.discover_all.return_value = [opp]
        self._scheduler._engine = engine

        result = self._scheduler.run_cycle()
        assert result["discovered"] == 1
        assert result["submitted"] == 0
        assert result["rejected"] == 1
        assert "confidence" in result["rejected_reasons"][0]["reason"]

    def test_run_cycle_rejects_high_risk(self):
        """High risk is rejected."""
        engine = MagicMock()
        opp = self._make_mock_opp(score=0.6, confidence=0.9, success_prob=0.1)
        engine.discover_all.return_value = [opp]
        self._scheduler._engine = engine

        result = self._scheduler.run_cycle()
        assert result["discovered"] == 1
        assert result["submitted"] == 0
        assert result["rejected"] == 1
        assert "risk" in result["rejected_reasons"][0]["reason"]

    def test_run_cycle_respects_max_per_cycle(self):
        """Only max_per_cycle opportunities are submitted per cycle."""
        engine = MagicMock()
        opps = [
            self._make_mock_opp(f"opp_{i}", score=0.9, confidence=0.9, success_prob=0.9)
            for i in range(10)
        ]
        engine.discover_all.return_value = opps
        self._scheduler._engine = engine
        self._queue.submit.return_value = ScheduledActivity(
            activity_id="test", node_type="opportunity",
        )

        result = self._scheduler.run_cycle()
        assert result["submitted"] == self._scheduler._max_per_cycle  # 5

    def test_run_cycle_skips_duplicates(self):
        """Already-submitted opportunities are not submitted again."""
        engine = MagicMock()
        opp = self._make_mock_opp(score=0.9, confidence=0.9, success_prob=0.9)
        engine.discover_all.return_value = [opp]
        self._scheduler._engine = engine
        self._queue.submit.return_value = ScheduledActivity(
            activity_id="test", node_type="opportunity",
        )

        # First cycle submits
        r1 = self._scheduler.run_cycle()
        assert r1["submitted"] == 1

        # Second cycle skips (already submitted + in _submitted_ids)
        r2 = self._scheduler.run_cycle()
        assert r2["discovered"] == 0  # filtered out by _submitted_ids

    def test_run_cycle_skips_non_open_opportunities(self):
        """Only OPEN opportunities are considered."""
        engine = MagicMock()
        opp = self._make_mock_opp()
        opp.status.value = "in_progress"
        engine.discover_all.return_value = [opp]
        self._scheduler._engine = engine

        result = self._scheduler.run_cycle()
        assert result["discovered"] == 0  # filtered before discovery count
        assert result["submitted"] == 0

    def test_score_to_priority_mapping(self):
        """_score_to_priority maps 0.0–1.0 to 1–5."""
        assert AutonomousScheduler._score_to_priority(0.9) == 5
        assert AutonomousScheduler._score_to_priority(0.7) == 4
        assert AutonomousScheduler._score_to_priority(0.5) == 3
        assert AutonomousScheduler._score_to_priority(0.3) == 2
        assert AutonomousScheduler._score_to_priority(0.1) == 1

    def test_evaluate_opportunity_with_decision_engine(self):
        """_evaluate_opportunity produces OpportunityActivity with decision metrics."""
        engine = MagicMock()
        self._scheduler._engine = engine

        opp = self._make_mock_opp(score=0.6, confidence=0.7, success_prob=0.8)
        bridge = self._scheduler._evaluate_opportunity(opp)

        assert bridge is not None
        assert bridge.opportunity_id == "opp_1"
        assert bridge.source_score == 0.6
        assert bridge.decision_confidence >= 0
        assert bridge.decision_risk >= 0


class TestAutonomousSchedulerWithRealIntelligence:
    """Integration tests with real ActivityIntelligence."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_auto_int.db")

        self._ai = ActivityIntelligence(db_path=self._db)
        self._engine = DecisionEngine(intelligence=self._ai)
        self._queue = MagicMock()
        self._scheduler = AutonomousScheduler(
            engine=None,
            decision=self._engine,
            queue=self._queue,
        )

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_evaluate_with_real_decision_engine(self):
        """Real DecisionEngine provides meaningful EV/risk values."""
        # Record some data so the engine has signal
        self._ai.record("h1", "opportunity", 5000, True)
        self._ai.record("h2", "opportunity", 5000, True)

        opp_mock = MagicMock()
        opp_mock.id = "opp_test"
        opp_mock.target_system = "browser_automation"
        opp_mock.improvement_description = "Test improvement"
        opp_mock.source = MagicMock()
        opp_mock.source.value = "bottleneck"
        opp_mock.opportunity_score = 0.7
        opp_mock.success_probability = 0.8
        opp_mock.confidence = 0.6
        opp_mock.status = MagicMock()
        opp_mock.status.value = "open"

        bridge = self._scheduler._evaluate_opportunity(opp_mock)
        assert bridge is not None
        assert bridge.decision_ev >= 0
        assert bridge.decision_confidence >= 0
        assert bridge.decision_risk >= 0
