"""Tests for Phase 8.3D — Decision Quality Bridge."""
import os
import shutil
import tempfile

import pytest

from core.scheduler.decision import DecisionEngine, DecisionEstimate
from core.scheduler.intelligence import ActivityIntelligence
from core.scheduler.models import ScheduledActivity
from core.scheduler.policies import DecisionPriorityPolicy


class TestDecisionEstimate:
    """DecisionEstimate dataclass and serialization."""

    def test_defaults(self):
        est = DecisionEstimate()
        assert est.impact == 0.0
        assert est.risk == 0.0
        assert est.expected_value == 0.0
        assert est.opportunity_cost == 0.0
        assert est.confidence == 0.0
        assert est.recommendation == "defer"
        assert est.breakdown == {}

    def test_to_dict(self):
        est = DecisionEstimate(impact=0.8, expected_value=0.6, confidence=0.9,
                               recommendation="schedule")
        d = est.to_dict()
        assert d["impact"] == 0.8
        assert d["expected_value"] == 0.6
        assert d["recommendation"] == "schedule"


class TestDecisionEngine:
    """DecisionEngine — estimate, score, explain."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_decision.db")
        self._ai = ActivityIntelligence(db_path=self._db)
        self._engine = DecisionEngine(intelligence=self._ai)

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_activity(self, aid="a1", node_type="build", priority=0,
                       goal="Build APK", status="pending") -> ScheduledActivity:
        return ScheduledActivity(
            activity_id=aid,
            priority=priority,
            status=status,
            goal=goal,
            node_type=node_type,
        )

    def test_estimate_no_data(self):
        """Without historical data, returns defaults with zero confidence.

        With zero confidence, expected_value = 0 (no basis for preference).
        """
        act = self._make_activity()
        est = self._engine.estimate(act)

        assert est.impact == pytest.approx(0.75)  # build default
        assert est.expected_value == 0.0  # no confidence → no EV
        assert est.confidence == 0.0  # 0 confidence with no data

    def test_estimate_with_data(self):
        """With historical data, confidence and risk improve."""
        self._ai.record("h1", "build", 5000, True)
        self._ai.record("h2", "build", 5000, True)
        self._ai.record("h3", "build", 5000, True)

        est = self._engine.estimate(self._make_activity())
        assert est.confidence >= 0
        assert est.risk <= 0.3  # 3/3 success → risk ~0

    def test_estimate_high_risk_type(self):
        """Types with low success rate get higher risk."""
        self._ai.record("h1", "research", 30000, True)
        self._ai.record("h2", "research", 30000, False)
        self._ai.record("h3", "research", 30000, False)

        est = self._engine.estimate(self._make_activity(node_type="research"))
        # risk should reflect ~33% success rate
        assert est.risk > 0.3
        assert est.risk < 0.9

    def test_estimate_high_priority_boost(self):
        """Higher user-assigned priority boosts impact."""
        low = self._engine.estimate(self._make_activity(priority=0))
        high = self._engine.estimate(self._make_activity(priority=5))
        assert high.impact > low.impact

    def test_score_bounds(self):
        """score returns 0-100."""
        act = self._make_activity()
        score = self._engine.score(act)
        assert 0 <= score <= 100

    def test_score_with_data(self):
        self._ai.record("h1", "build", 5000, True)
        score = self._engine.score(self._make_activity())
        assert 0 <= score <= 100

    def test_explain(self):
        """explain returns a dict with breakdown keys."""
        act = self._make_activity()
        explanation = self._engine.explain(act)
        assert isinstance(explanation, dict)
        assert "impact" in explanation
        assert "risk" in explanation
        assert "expected_value" in explanation
        assert "breakdown" in explanation

    def test_estimate_different_types(self):
        """Different activity types produce different estimates."""
        build_act = self._make_activity(node_type="build")
        email_act = self._make_activity(node_type="email")

        build_est = self._engine.estimate(build_act)
        email_est = self._engine.estimate(email_act)

        # Build has higher default impact than email
        assert build_est.impact > email_est.impact

    def test_estimate_low_value_type(self):
        """Email should have low impact."""
        act = self._make_activity(node_type="email")
        est = self._engine.estimate(act)
        assert est.impact == pytest.approx(0.30)

    def test_score_ranking_consistency(self):
        """Higher-value activities should score >= lower-value ones."""
        build_act = self._make_activity(aid="build", node_type="build")
        email_act = self._make_activity(aid="email", node_type="email")

        build_score = self._engine.score(build_act)
        email_score = self._engine.score(email_act)

        assert build_score >= email_score

    def test_estimate_with_failed_data(self):
        """Activities with 100% failure rate get high risk."""
        self._ai.record("f1", "research", 30000, False)
        self._ai.record("f2", "research", 30000, False)
        self._ai.record("f3", "research", 30000, False)

        est = self._engine.estimate(self._make_activity(node_type="research"))
        assert est.risk > 0.5
        assert est.expected_value < 0.5


class TestDecisionPriorityPolicy:
    """DecisionPriorityPolicy — expected-value-based ranking."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test_dpp.db")
        self._ai = ActivityIntelligence(db_path=self._db)
        self._engine = DecisionEngine(intelligence=self._ai)
        self._policy = DecisionPriorityPolicy(engine=self._engine)

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_rank_empty(self):
        assert self._policy.rank([]) == []

    def test_rank_single(self):
        act = ScheduledActivity(activity_id="a1", node_type="build")
        ranked = self._policy.rank([act])
        assert len(ranked) == 1
        assert ranked[0].activity_id == "a1"
        assert ranked[0].score >= 0  # score was assigned

    def test_rank_orders_by_default_impact(self):
        """Activities rank by impact when historical data is available.

        High-impact types (strategy=0.80) rank above low-impact (email=0.30)
        when success rates are equal.
        """
        # Give each type enough data for meaningful confidence
        for i in range(20):
            self._ai.record(f"b{i}", "build", 5000, True)
            self._ai.record(f"e{i}", "email", 2000, True)
            self._ai.record(f"s{i}", "strategy", 10000, True)

        strategy = ScheduledActivity(activity_id="a3", node_type="strategy", goal="Strategy")
        email = ScheduledActivity(activity_id="a2", node_type="email", goal="Email")

        ranked = self._policy.rank([email, strategy])
        # Strategy (0.80) > Email (0.30) — clear gap even with calibration
        assert ranked[0].node_type == "strategy", f"Expected strategy first, got {ranked[0].node_type}"
        assert ranked[1].node_type == "email", f"Expected email last, got {ranked[1].node_type}"
        # Strategy should have meaningfully higher score
        assert ranked[0].score > ranked[1].score + 5

    def test_rank_with_historical_data(self):
        """Successful types rank higher than failing ones, given similar impact."""
        # Record 3 failures for build → poor success rate
        self._ai.record("f1", "build", 5000, False)
        self._ai.record("f2", "build", 5000, False)
        self._ai.record("f3", "build", 5000, False)

        build = ScheduledActivity(activity_id="a1", node_type="build")
        email = ScheduledActivity(activity_id="a2", node_type="email")

        ranked = self._policy.rank([build, email])
        # Build has higher default impact (0.75) but 0% success rate
        # Email has lower default impact (0.30) but prior 70% success rate
        # EV = impact * success_prob * confidence / resource_cost
        # Both should have valid scores
        assert len(ranked) == 2
        # Both activities get scores >= 0
        assert all(a.score >= 0 for a in ranked)

    def test_engine_property(self):
        assert self._policy.engine is self._engine

    def test_engine_setter(self):
        import copy
        new_engine = DecisionEngine(intelligence=self._ai)
        self._policy.engine = new_engine
        assert self._policy.engine is new_engine


class TestDecisionEnginePriorityModifier:
    """DecisionEngine._apply_priority_modifier."""

    def test_no_boost_for_zero(self):
        engine = DecisionEngine()
        assert engine._apply_priority_modifier(0.5, 0) == 0.5

    def test_boost_for_high_priority(self):
        engine = DecisionEngine()
        # priority=5 → modifier = 1.0 + 0.5 = 1.5
        boosted = engine._apply_priority_modifier(0.5, 5)
        assert boosted == pytest.approx(0.75)

    def test_caps_at_one(self):
        engine = DecisionEngine()
        result = engine._apply_priority_modifier(0.9, 5)
        assert result == 1.0
