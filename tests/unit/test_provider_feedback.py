"""Tests for X.6 — Decision Feedback Engine.

Covers: models, FeedbackStore, DecisionRecorder, CalibrationEngine,
and integration with Router + Orchestrator.
"""

import json
import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from core.providers.feedback.models import (
    CalibrationEntry, RoutingDecision, RoutingOutcome, ScoreBreakdown,
)
from core.providers.feedback.store import FeedbackStore
from core.providers.feedback.recorder import DecisionRecorder
from core.providers.feedback.calibrator import CalibrationEngine


# ═════════════════════════════════════════════════════════════════════════════
# Models
# ═════════════════════════════════════════════════════════════════════════════

class TestModels:
    def test_score_breakdown_roundtrip(self):
        sb = ScoreBreakdown(
            provider_id="forge",
            priority_score=0.4, historical_score=0.3,
            benchmark_score=0.15, calibration_adjustment=0.05,
            total_score=0.9,
        )
        d = sb.to_dict()
        restored = ScoreBreakdown.from_dict(d)
        assert restored.provider_id == "forge"
        assert restored.priority_score == 0.4
        assert restored.total_score == 0.9

    def test_routing_decision_roundtrip(self):
        d = RoutingDecision(
            decision_id="dec_test",
            goal="Write a function",
            capability="coding",
            task={"goal": "Write a function"},
            selected_provider="forge",
            candidate_scores=[
                ScoreBreakdown(provider_id="forge", total_score=0.9),
                ScoreBreakdown(provider_id="codex", total_score=0.7),
            ],
            excluded_providers=["bad_test"],
            timestamp=1000.0,
        )
        d2 = RoutingDecision.from_dict(d.to_dict())
        assert d2.decision_id == "dec_test"
        assert d2.selected_provider == "forge"
        assert len(d2.candidate_scores) == 2
        assert d2.candidate_scores[0].total_score == 0.9
        assert "bad_test" in d2.excluded_providers

    def test_routing_decision_defaults(self):
        d = RoutingDecision()
        assert d.decision_id.startswith("dec_")
        assert d.capability == ""
        assert d.candidate_scores == []

    def test_routing_outcome_roundtrip(self):
        o = RoutingOutcome(
            outcome_id="out_test", decision_id="dec_test",
            success=True, duration_ms=1500.0, quality_score=0.85,
            cost=0.02, retries=1, replan_level=0, timestamp=2000.0,
        )
        o2 = RoutingOutcome.from_dict(o.to_dict())
        assert o2.outcome_id == "out_test"
        assert o2.success is True
        assert o2.duration_ms == 1500.0

    def test_outcome_score_composite(self):
        # Perfect outcome
        o1 = RoutingOutcome(success=True, quality_score=1.0, duration_ms=100)
        assert o1.outcome_score > 0.9

        # Failed outcome
        o2 = RoutingOutcome(success=False, quality_score=0.0, duration_ms=0)
        assert o2.outcome_score < 0.1

        # Replan penalty
        o3 = RoutingOutcome(success=True, quality_score=0.8, duration_ms=1000, replan_level=3)
        assert o3.outcome_score < 0.8

    def test_outcome_score_edge_cases(self):
        # Zero values
        o = RoutingOutcome()
        assert o.outcome_score == 0.0

        # Long duration
        o2 = RoutingOutcome(success=True, quality_score=1.0, duration_ms=600000)
        assert o2.outcome_score >= 0.5  # duration factor floors at 0

    def test_calibration_entry_roundtrip(self):
        e = CalibrationEntry(
            entry_id="cal_test", provider_id="forge",
            capability="coding", adjustment=0.05,
            confidence=0.8, evidence_count=10, last_updated=3000.0,
        )
        d = e.to_dict()
        assert d["provider_id"] == "forge"
        assert d["adjustment"] == 0.05


# ═════════════════════════════════════════════════════════════════════════════
# FeedbackStore
# ═════════════════════════════════════════════════════════════════════════════

class TestFeedbackStore:
    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_feedback.db")
            s = FeedbackStore(db_path=db_path)
            yield s
            s.close()

    def _decision(self, **kw):
        defaults = dict(goal="test", capability="coding", selected_provider="forge")
        defaults.update(kw)
        return RoutingDecision(**defaults)

    def _outcome(self, **kw):
        defaults = dict(decision_id="dec_1", success=True)
        defaults.update(kw)
        return RoutingOutcome(**defaults)

    def _calibration(self, **kw):
        defaults = dict(provider_id="forge", capability="coding")
        defaults.update(kw)
        return CalibrationEntry(**defaults)

    def test_save_and_get_decision(self, store):
        decision = RoutingDecision(
            goal="test goal", capability="coding",
            selected_provider="forge",
        )
        store.save_decision(decision)
        loaded = store.get_decision(decision.decision_id)
        assert loaded is not None
        assert loaded.goal == "test goal"
        assert loaded.selected_provider == "forge"

    def test_save_decision_with_candidates(self, store):
        decision = RoutingDecision(
            goal="test",
            candidate_scores=[
                ScoreBreakdown(provider_id="forge", total_score=0.9),
                ScoreBreakdown(provider_id="codex", total_score=0.7),
            ],
        )
        store.save_decision(decision)
        loaded = store.get_decision(decision.decision_id)
        assert len(loaded.candidate_scores) == 2

    def test_get_decision_not_found(self, store):
        loaded = store.get_decision("nonexistent")
        assert loaded is None

    def test_recent_decisions(self, store):
        for i in range(5):
            d = RoutingDecision(goal=f"goal {i}", timestamp=float(i))
            store.save_decision(d)
        recent = store.get_recent_decisions(limit=3)
        assert len(recent) == 3
        # Most recent first (highest timestamp)
        assert recent[0].goal == "goal 4"
        assert recent[2].goal == "goal 2"

    def test_count_decisions(self, store):
        assert store.count_decisions() == 0
        store.save_decision(RoutingDecision(capability="coding"))
        store.save_decision(RoutingDecision(capability="coding"))
        store.save_decision(RoutingDecision(capability="testing"))
        assert store.count_decisions() == 3
        assert store.count_decisions(capability="coding") == 2

    def test_save_and_get_outcome(self, store):
        outcome = RoutingOutcome(
            decision_id="dec_1", success=True,
            duration_ms=100.0, quality_score=0.9,
        )
        store.save_outcome(outcome)
        outcomes = store.get_outcomes_for_decision("dec_1")
        assert len(outcomes) == 1
        assert outcomes[0].success is True
        assert outcomes[0].quality_score == 0.9

    def test_get_outcomes_for_decision_empty(self, store):
        assert store.get_outcomes_for_decision("nonexistent") == []

    def test_get_all_outcomes_filtered(self, store):
        # Save decisions first
        d1 = RoutingDecision(goal="g1", capability="coding", selected_provider="forge")
        d2 = RoutingDecision(goal="g2", capability="testing", selected_provider="codex")
        store.save_decision(d1)
        store.save_decision(d2)

        # Save outcomes
        store.save_outcome(RoutingOutcome(decision_id=d1.decision_id, success=True))
        store.save_outcome(RoutingOutcome(decision_id=d2.decision_id, success=False))

        # Filter by provider
        outcomes = store.get_all_outcomes(provider_id="forge")
        assert len(outcomes) == 1
        assert outcomes[0].success is True

        # Filter by capability
        outcomes = store.get_all_outcomes(capability="testing")
        assert len(outcomes) == 1
        assert outcomes[0].success is False

        # Filter by both
        outcomes = store.get_all_outcomes(provider_id="forge", capability="coding")
        assert len(outcomes) == 1

        # Filter by non-matching both
        outcomes = store.get_all_outcomes(provider_id="forge", capability="testing")
        assert len(outcomes) == 0

    def test_calibration_crud(self, store):
        entry = CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.05, confidence=0.8, evidence_count=10,
        )
        store.save_calibration(entry)

        loaded = store.get_calibration("forge", "coding")
        assert loaded is not None
        assert loaded.adjustment == 0.05
        assert loaded.confidence == 0.8

        # Update
        entry.adjustment = 0.08
        entry.evidence_count = 15
        store.save_calibration(entry)
        loaded = store.get_calibration("forge", "coding")
        assert loaded.adjustment == 0.08
        assert loaded.evidence_count == 15

    def test_get_calibration_not_found(self, store):
        assert store.get_calibration("nonexistent", "coding") is None

    def test_get_all_calibrations(self, store):
        store.save_calibration(CalibrationEntry(provider_id="forge", capability="coding"))
        store.save_calibration(CalibrationEntry(provider_id="codex", capability="testing"))
        all_cal = store.get_all_calibrations()
        assert len(all_cal) == 2

    def test_provider_stats(self, store):
        d1 = RoutingDecision(capability="coding", selected_provider="forge")
        store.save_decision(d1)
        store.save_outcome(RoutingOutcome(
            decision_id=d1.decision_id, success=True,
            duration_ms=100, quality_score=0.9, cost=0.01,
        ))
        d2 = RoutingDecision(capability="coding", selected_provider="forge")
        store.save_decision(d2)
        store.save_outcome(RoutingOutcome(
            decision_id=d2.decision_id, success=False,
            duration_ms=200, quality_score=0.3, cost=0.02,
        ))

        stats = store.get_provider_stats("forge")
        assert stats["total"] == 2
        assert stats["success_rate"] == 0.5
        assert stats["avg_duration_ms"] == 150.0
        assert stats["avg_quality"] == 0.6

    def test_provider_stats_no_data(self, store):
        stats = store.get_provider_stats("nonexistent")
        assert stats["total"] == 0

    def test_calibration_summary(self, store):
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.05, confidence=0.8, evidence_count=10,
        ))
        summary = store.get_calibration_summary()
        assert len(summary) == 1
        assert summary[0]["provider_id"] == "forge"
        assert summary[0]["adjustment"] == 0.05

    def test_clear(self, store):
        store.save_decision(RoutingDecision())
        store.save_outcome(RoutingOutcome(decision_id="dec_1"))
        store.save_calibration(CalibrationEntry(provider_id="f", capability="c"))
        store.clear()
        assert store.count_decisions() == 0
        assert store.get_all_outcomes() == []
        assert store.get_all_calibrations() == []


# ═════════════════════════════════════════════════════════════════════════════
# DecisionRecorder
# ═════════════════════════════════════════════════════════════════════════════

class TestDecisionRecorder:
    @pytest.fixture
    def recorder(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_recorder.db")
            store = FeedbackStore(db_path=db_path)
            yield DecisionRecorder(store=store)
            store.close()

    def test_record_decision(self, recorder):
        decision = recorder.record_decision(
            capability="coding",
            task={"goal": "Write code"},
            selected_provider="forge",
            candidate_scores=[
                ScoreBreakdown(provider_id="forge", total_score=0.9),
            ],
        )
        assert decision.decision_id.startswith("dec_")
        assert decision.capability == "coding"
        assert decision.selected_provider == "forge"

        # Verify persisted
        loaded = recorder._store.get_decision(decision.decision_id)
        assert loaded is not None

    def test_record_outcome(self, recorder):
        decision = recorder.record_decision("coding", {}, "forge", [])
        outcome = recorder.record_outcome(
            decision_id=decision.decision_id,
            success=True, duration_ms=500.0, quality_score=0.85,
            cost=0.01, retries=1,
        )
        assert outcome.outcome_id.startswith("out_")
        assert outcome.success is True
        assert outcome.duration_ms == 500.0

        # Verify linked
        outcomes = recorder._store.get_outcomes_for_decision(decision.decision_id)
        assert len(outcomes) == 1

    def test_get_provider_performance(self, recorder):
        # No data yet
        stats = recorder.get_provider_performance("forge")
        assert stats["total"] == 0

        # Add data
        d = recorder.record_decision("coding", {}, "forge", [])
        recorder.record_outcome(decision_id=d.decision_id, success=True)
        d2 = recorder.record_decision("coding", {}, "forge", [])
        recorder.record_outcome(decision_id=d2.decision_id, success=False)

        stats = recorder.get_provider_performance("forge")
        assert stats["total"] == 2
        assert stats["success_rate"] == 0.5

    def test_get_recent_decisions(self, recorder):
        for i in range(5):
            recorder.record_decision(f"cap_{i}", {}, f"prov_{i}", [])
        recent = recorder.get_recent_decisions(limit=3)
        assert len(recent) == 3


# ═════════════════════════════════════════════════════════════════════════════
# CalibrationEngine
# ═════════════════════════════════════════════════════════════════════════════

class TestCalibrationEngine:
    @pytest.fixture
    def engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_calibrator.db")
            store = FeedbackStore(db_path=db_path)
            yield CalibrationEngine(store=store)
            store.close()

    def _add_outcome(self, store: FeedbackStore, provider_id: str, capability: str,
                     success: bool, quality: float = 0.5, duration_ms: float = 1000.0,
                     replan_level: int = 0):
        d = RoutingDecision(capability=capability, selected_provider=provider_id)
        store.save_decision(d)
        store.save_outcome(RoutingOutcome(
            decision_id=d.decision_id, success=success,
            quality_score=quality, duration_ms=duration_ms,
            replan_level=replan_level,
        ))

    def test_get_adjustment_no_data(self, engine):
        adj = engine.get_adjustment("forge", "coding")
        assert adj == 0.0

    def test_get_adjustment_with_confidence_no_data(self, engine):
        adj, conf = engine.get_adjustment_with_confidence("forge", "coding")
        assert adj == 0.0
        assert conf == 0.0

    def test_update_from_outcomes_insufficient_evidence(self, engine):
        self._add_outcome(engine._store, "forge", "coding", True)
        result = engine.update_from_outcomes("forge", "coding")
        assert result is None  # Not enough evidence (< min_evidence)

    def test_update_from_outcomes_sufficient(self, engine):
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding", True, quality=0.9)
        result = engine.update_from_outcomes("forge", "coding")
        assert result is not None
        assert result.adjustment > 0  # Above baseline 0.75
        assert result.confidence > 0
        assert result.evidence_count >= 5

    def test_update_from_outcomes_poor_performance(self, engine):
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding",
                              success=False, quality=0.1)
        result = engine.update_from_outcomes("forge", "coding")
        assert result is not None
        assert result.adjustment < 0  # Below baseline
        assert result.confidence > 0

    def test_get_adjustment_after_update(self, engine):
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding", True, quality=0.9)
        engine.update_from_outcomes("forge", "coding")
        adj = engine.get_adjustment("forge", "coding")
        assert adj > 0.0

    def test_get_adjustment_after_poor_update(self, engine):
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding",
                              success=False, quality=0.1)
        engine.update_from_outcomes("forge", "coding")
        adj = engine.get_adjustment("forge", "coding")
        assert adj < 0.0

    def test_update_all_no_data(self, engine):
        count = engine.update_all()
        assert count == 0

    def test_update_all_with_data(self, engine):
        self._add_outcome(engine._store, "forge", "coding", True, quality=0.95)
        self._add_outcome(engine._store, "forge", "coding", True, quality=0.85)
        self._add_outcome(engine._store, "forge", "coding", True, quality=0.90)
        self._add_outcome(engine._store, "forge", "coding", True, quality=0.80)
        self._add_outcome(engine._store, "forge", "coding", True, quality=0.88)
        count = engine.update_all()
        assert count >= 1

    def test_force_update_with_few_outcomes(self, engine):
        self._add_outcome(engine._store, "forge", "coding", True, quality=0.9)
        result = engine.update_from_outcomes("forge", "coding", force=True)
        assert result is not None

    def test_confidence_saturates_with_evidence(self, engine):
        for _ in range(60):  # Above max_evidence (50)
            self._add_outcome(engine._store, "forge", "coding", True, quality=0.85)

        engine.update_from_outcomes("forge", "coding")
        adj, conf = engine.get_adjustment_with_confidence("forge", "coding")
        assert conf <= 1.0
        assert conf > 0.8

    def test_get_summary(self, engine):
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding", True, quality=0.9)
        engine.update_from_outcomes("forge", "coding")
        summary = engine.get_summary()
        assert len(summary) >= 1
        assert summary[0]["provider_id"] == "forge"
        assert "adjustment" in summary[0]

    def test_multiple_providers(self, engine):
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding", True, quality=0.9)
        for _ in range(5):
            self._add_outcome(engine._store, "codex", "coding", False, quality=0.2)
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "testing", True, quality=0.7)

        engine.update_from_outcomes("forge", "coding")
        engine.update_from_outcomes("codex", "coding")
        engine.update_from_outcomes("forge", "testing")

        adj_forge, conf_forge = engine.get_adjustment_with_confidence("forge", "coding")
        adj_codex, conf_codex = engine.get_adjustment_with_confidence("codex", "coding")

        assert adj_forge > adj_codex  # forge outperforms codex
        assert conf_forge > 0
        assert conf_codex > 0


# ═════════════════════════════════════════════════════════════════════════════
# Integration: Router calibration integration
# ═════════════════════════════════════════════════════════════════════════════

class TestRouterFeedbackIntegration:
    @pytest.fixture(autouse=True)
    def _ensure_providers(self):
        from core.providers.bootstrap import register_internal_providers
        register_internal_providers()
        yield

    def test_router_score_includes_calibration(self):
        from core.providers.router import ProviderRouter
        from core.providers.registry import provider_registry
        forge = provider_registry.get("forge")
        if forge is None:
            return
        router = ProviderRouter()
        score_before = router._score(forge, {"capability": "coding"})
        cal_engine = router._get_calibration_engine()
        if cal_engine:
            store = cal_engine._store
            for _ in range(5):
                d = RoutingDecision(capability="coding", selected_provider="forge")
                store.save_decision(d)
                store.save_outcome(RoutingOutcome(decision_id=d.decision_id, success=True, quality_score=0.95, duration_ms=100))
            cal_engine.update_from_outcomes("forge", "coding")
            score_after = router._score(forge, {"capability": "coding"})
            assert score_after != score_before
            store.close()

    def test_select_records_decision(self):
        from core.providers.router import ProviderRouter
        from core.providers.registry import provider_registry
        forge = provider_registry.get("forge")
        if forge is None:
            return
        router = ProviderRouter()
        provider = router.select("coding", {"goal": "test"}, record_decision=True)
        assert provider is not None
        assert router.last_decision_id is not None

    @pytest.mark.asyncio
    async def test_orchestrator_feedback_loop(self):
        from core.providers.orchestration.planner import OrchestrationPlanner
        from core.providers.orchestration.orchestrator import Orchestrator
        planner = OrchestrationPlanner()
        plan = planner.plan("Write a function")
        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        fb = orchestrator._get_feedback()
        assert fb is not None
        store = fb["recorder"]._store
        decisions = store.get_recent_decisions(limit=10)
        decisions_with_outcomes = 0
        for d in decisions:
            outcomes = store.get_outcomes_for_decision(d.decision_id)
            if outcomes:
                decisions_with_outcomes += 1
        assert decisions_with_outcomes > 0
        calibrator = fb["calibrator"]
        summary = calibrator.get_summary()
        assert summary is not None
        store.close()


# ═════════════════════════════════════════════════════════════════════════════
# Integration: Planner records decision ID in task
# ═════════════════════════════════════════════════════════════════════════════

class TestPlannerDecisionRecording:
    def test_planner_records_decision_id(self):
        """Planner should store decision_id in step task when router selects."""
        from core.providers.orchestration.planner import OrchestrationPlanner
        from core.providers.registry import provider_registry

        # Ensure forge is registered so the router can select it
        forge = provider_registry.get("forge")
        if forge is None:
            return  # skip if no forge registered

        planner = OrchestrationPlanner()
        plan = planner.plan("Write a function")
        found = False
        for step in plan.steps:
            if "_decision_id" in step.task:
                found = True
                assert step.task["_decision_id"].startswith("dec_")
        assert found, "At least one step should have a decision_id"
