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
    context_key, _CONTEXT_FALLBACK_CHAIN, _extract_context,
)
from core.providers.feedback.store import FeedbackStore
from core.providers.feedback.recorder import DecisionRecorder
from core.providers.feedback.calibrator import CalibrationEngine
from core.providers.feedback.models import ProviderResult as _ProviderResult
from core.providers.memory import provider_memory


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
            task={"goal": "Write a function", "language": "python"},
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

    def test_routing_decision_context_properties(self):
        d = RoutingDecision(task={"language": "python", "framework": "fastapi"})
        assert d.language == "python"
        assert d.framework == "fastapi"

        d2 = RoutingDecision(task={"goal": "test"})
        assert d2.language == ""

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
        o1 = RoutingOutcome(success=True, quality_score=1.0, duration_ms=100)
        assert o1.outcome_score > 0.9

        o2 = RoutingOutcome(success=False, quality_score=0.0, duration_ms=0)
        assert o2.outcome_score < 0.1

        o3 = RoutingOutcome(success=True, quality_score=0.8, duration_ms=1000, replan_level=3)
        assert o3.outcome_score < 0.8

    def test_outcome_score_edge_cases(self):
        o = RoutingOutcome()
        assert o.outcome_score == 0.0

        o2 = RoutingOutcome(success=True, quality_score=1.0, duration_ms=600000)
        assert o2.outcome_score >= 0.5

    def test_calibration_entry_roundtrip(self):
        e = CalibrationEntry(
            entry_id="cal_test", provider_id="forge",
            capability="coding", adjustment=0.05,
            confidence=0.8, evidence_count=10, last_updated=3000.0,
            language="python", framework="fastapi",
        )
        d = e.to_dict()
        assert d["provider_id"] == "forge"
        assert d["adjustment"] == 0.05
        assert d["language"] == "python"
        assert d["framework"] == "fastapi"
        restored = CalibrationEntry.from_dict(d)
        assert restored.language == "python"
        assert restored.framework == "fastapi"

    def test_calibration_entry_context_fields_default(self):
        e = CalibrationEntry(provider_id="p", capability="c")
        assert e.language == ""
        assert e.framework == ""
        assert e.project_size == ""

    def test_context_key(self):
        key = context_key("coding", "python", "fastapi", "small")
        assert key == ("coding", "python", "fastapi", "small")

        key2 = context_key("coding")
        assert key2 == ("coding", "", "", "")

    def test_extract_context(self):
        ctx = _extract_context({"language": "py", "framework": "fj", "project_size": "large"})
        assert ctx == {"language": "py", "framework": "fj", "project_size": "large"}

        ctx2 = _extract_context({})
        assert ctx2 == {"language": "", "framework": "", "project_size": ""}

        ctx3 = _extract_context(None)
        assert ctx3 == {"language": "", "framework": "", "project_size": ""}

    def test_fallback_chain_structure(self):
        assert len(_CONTEXT_FALLBACK_CHAIN) == 4
        # Most specific first: language + framework + project_size
        assert _CONTEXT_FALLBACK_CHAIN[0] == (3, 2, 1)
        # Generic last
        assert _CONTEXT_FALLBACK_CHAIN[-1] == (0, 0, 0)

    def test_calibration_config_defaults(self):
        from core.providers.feedback.models import CalibrationConfig
        cfg = CalibrationConfig()
        assert cfg.half_life_days == 100.0
        assert cfg.minimum_weight == 0.05
        assert cfg.maximum_history_days == 365
        assert cfg.min_evidence == 3
        assert cfg.max_evidence == 50
        assert cfg.alpha == 0.3

    def test_calibration_config_custom(self):
        from core.providers.feedback.models import CalibrationConfig
        cfg = CalibrationConfig(half_life_days=30.0, max_evidence=100)
        assert cfg.half_life_days == 30.0
        assert cfg.max_evidence == 100

    def test_compute_time_weights(self):
        import time
        from core.providers.feedback.models import _compute_time_weights
        now = time.time()
        recent = now - 1000
        old = now - (200 * 86400)

        weights, effective_n = _compute_time_weights(
            [recent, old],
            half_life_days=100.0, max_history_days=365, min_weight=0.05, now=now,
        )
        assert len(weights) == 2
        assert weights[0] > weights[1]
        assert effective_n > 0

    def test_compute_time_weights_old_filtered(self):
        import time
        from core.providers.feedback.models import _compute_time_weights
        now = time.time()
        very_old = now - (500 * 86400)

        weights, effective_n = _compute_time_weights(
            [very_old],
            half_life_days=100.0, max_history_days=365, min_weight=0.05, now=now,
        )
        assert weights == []
        assert effective_n == 0.0

    def test_compute_time_weights_future_timestamp(self):
        import time
        from core.providers.feedback.models import _compute_time_weights
        now = time.time()
        future = now + 3600

        weights, effective_n = _compute_time_weights(
            [future],
            half_life_days=100.0, max_history_days=365, min_weight=0.05, now=now,
        )
        assert len(weights) == 1
        assert weights[0] > 0.99

    def test_compute_time_weights_empty(self):
        from core.providers.feedback.models import _compute_time_weights
        weights, effective_n = _compute_time_weights([], now=0)
        assert weights == []
        assert effective_n == 0.0


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
        import time
        defaults = dict(goal="test", capability="coding", selected_provider="forge", timestamp=time.time())
        defaults.update(kw)
        return RoutingDecision(**defaults)

    def _outcome(self, **kw):
        import time
        defaults = dict(decision_id="dec_1", success=True, timestamp=time.time())
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
        d1 = RoutingDecision(goal="g1", capability="coding", selected_provider="forge")
        d2 = RoutingDecision(goal="g2", capability="testing", selected_provider="codex")
        store.save_decision(d1)
        store.save_decision(d2)

        store.save_outcome(RoutingOutcome(decision_id=d1.decision_id, success=True))
        store.save_outcome(RoutingOutcome(decision_id=d2.decision_id, success=False))

        outcomes = store.get_all_outcomes(provider_id="forge")
        assert len(outcomes) == 1
        assert outcomes[0].success is True

        outcomes = store.get_all_outcomes(capability="testing")
        assert len(outcomes) == 1
        assert outcomes[0].success is False

        outcomes = store.get_all_outcomes(provider_id="forge", capability="coding")
        assert len(outcomes) == 1

        outcomes = store.get_all_outcomes(provider_id="forge", capability="testing")
        assert len(outcomes) == 0

    # ── Context-aware calibration CRUD ─────────────────────────────

    def test_calibration_crud_without_context(self, store):
        entry = CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.05, confidence=0.8, evidence_count=10,
        )
        store.save_calibration(entry)

        loaded = store.get_calibration("forge", "coding")
        assert loaded is not None
        assert loaded.adjustment == 0.05
        assert loaded.confidence == 0.8

        entry.adjustment = 0.08
        entry.evidence_count = 15
        store.save_calibration(entry)
        loaded = store.get_calibration("forge", "coding")
        assert loaded.adjustment == 0.08
        assert loaded.evidence_count == 15

    def test_calibration_crud_with_context(self, store):
        entry = CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.05, confidence=0.8, evidence_count=10,
            language="python", framework="fastapi", project_size="medium",
        )
        store.save_calibration(entry)

        loaded = store.get_calibration(
            "forge", "coding",
            language="python", framework="fastapi", project_size="medium",
        )
        assert loaded is not None
        assert loaded.adjustment == 0.05
        assert loaded.language == "python"
        assert loaded.framework == "fastapi"
        assert loaded.project_size == "medium"

        # Without context — should not match
        loaded = store.get_calibration("forge", "coding")
        assert loaded is None

    def test_calibration_context_uniqueness(self, store):
        e1 = CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.1, language="python",
        )
        e2 = CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.2, language="javascript",
        )
        e3 = CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.3,
        )
        store.save_calibration(e1)
        store.save_calibration(e2)
        store.save_calibration(e3)

        py = store.get_calibration("forge", "coding", language="python")
        assert py.adjustment == 0.1

        js = store.get_calibration("forge", "coding", language="javascript")
        assert js.adjustment == 0.2

        generic = store.get_calibration("forge", "coding")
        assert generic.adjustment == 0.3

    def test_get_calibration_not_found(self, store):
        assert store.get_calibration("nonexistent", "coding") is None

    def test_get_all_calibrations(self, store):
        store.save_calibration(CalibrationEntry(provider_id="forge", capability="coding"))
        store.save_calibration(CalibrationEntry(provider_id="codex", capability="testing"))
        all_cal = store.get_all_calibrations()
        assert len(all_cal) == 2

    # ── Fallback chain ──────────────────────────────────────────────

    def test_calibration_fallback_precise_first(self, store):
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.1, language="python", framework="fastapi",
        ))
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.2,
        ))
        # Should find the more specific match first
        result = store.get_calibration_fallback(
            "forge", "coding",
            language="python", framework="fastapi",
        )
        assert result is not None
        assert result.adjustment == 0.1
        assert result.language == "python"
        assert result.framework == "fastapi"

    def test_calibration_fallback_language_only(self, store):
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.15, language="python",
        ))
        result = store.get_calibration_fallback(
            "forge", "coding",
            language="python", framework="django",
        )
        assert result is not None
        assert result.adjustment == 0.15
        assert result.language == "python"

    def test_calibration_fallback_generic(self, store):
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.05,
        ))
        result = store.get_calibration_fallback(
            "forge", "coding",
            language="python", framework="django",
        )
        assert result is not None
        assert result.adjustment == 0.05
        assert result.language == ""

    def test_calibration_fallback_none_found(self, store):
        result = store.get_calibration_fallback("forge", "nonexistent")
        assert result is None

    def test_calibration_fallback_partial_framework(self, store):
        """Should match language-only before generic when framework known."""
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.1, language="python",
        ))
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.3,
        ))
        result = store.get_calibration_fallback(
            "forge", "coding",
            language="python", framework="flask",
        )
        assert result is not None
        assert result.adjustment == 0.1

    def test_calibration_fallback_project_size(self, store):
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.25, language="python", framework="fastapi",
            project_size="large",
        ))
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.15, language="python", framework="fastapi",
        ))
        # Should match the large-specific one
        result = store.get_calibration_fallback(
            "forge", "coding",
            language="python", framework="fastapi", project_size="large",
        )
        assert result is not None
        assert result.adjustment == 0.25

        # Should fallback to the non-size one
        result = store.get_calibration_fallback(
            "forge", "coding",
            language="python", framework="fastapi", project_size="small",
        )
        assert result is not None
        assert result.adjustment == 0.15

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

        outcomes = recorder._store.get_outcomes_for_decision(decision.decision_id)
        assert len(outcomes) == 1

    def test_get_provider_performance(self, recorder):
        stats = recorder.get_provider_performance("forge")
        assert stats["total"] == 0

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
# CalibrationEngine (context-aware)
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
                     replan_level: int = 0, timestamp: float | None = None,
                     **task_kw):
        import time
        task = {"language": "", "framework": "", "project_size": ""}
        task.update(task_kw)
        now = timestamp if timestamp is not None else time.time()
        d = RoutingDecision(
            capability=capability, selected_provider=provider_id,
            task=task, timestamp=now,
        )
        store.save_decision(d)
        store.save_outcome(RoutingOutcome(
            decision_id=d.decision_id, success=success,
            quality_score=quality, duration_ms=duration_ms,
            replan_level=replan_level, timestamp=now,
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
        count = engine.update_from_outcomes("forge", "coding")
        assert count == 0

    def test_update_from_outcomes_sufficient(self, engine):
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding", True, quality=0.9)
        count = engine.update_from_outcomes("forge", "coding")
        assert count >= 1

        adj = engine.get_adjustment("forge", "coding")
        assert adj > 0

    def test_update_from_outcomes_poor_performance(self, engine):
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding",
                              success=False, quality=0.1)
        count = engine.update_from_outcomes("forge", "coding")
        assert count >= 1

        adj = engine.get_adjustment("forge", "coding")
        assert adj < 0

    def test_force_update_with_few_outcomes(self, engine):
        self._add_outcome(engine._store, "forge", "coding", True, quality=0.9)
        entry = engine.update_from_outcomes_for_context(
            "forge", "coding", force=True,
        )
        assert entry is not None

    def test_confidence_saturates_with_evidence(self, engine):
        for _ in range(60):
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

        assert adj_forge > adj_codex
        assert conf_forge > 0
        assert conf_codex > 0

    def test_update_all_no_data(self, engine):
        count = engine.update_all()
        assert count == 0

    def test_update_all_with_data(self, engine):
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding", True, quality=0.9)
        count = engine.update_all()
        assert count >= 1

    # ── Context-aware calibration ──────────────────────────────────

    def test_context_aware_calibration_python_better(self, engine):
        """Python outcomes are good, JS outcomes are bad. Verify python
        gets a higher adjustment than JS than generic."""
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding", True, quality=0.95,
                language="python",
            )
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding", False, quality=0.1,
                language="javascript",
            )

        engine.update_from_outcomes("forge", "coding")

        py_adj = engine.get_adjustment("forge", "coding",
                                        language="python")
        js_adj = engine.get_adjustment("forge", "coding",
                                        language="javascript")
        generic_adj = engine.get_adjustment("forge", "coding")

        assert py_adj > generic_adj
        assert js_adj < generic_adj

    def test_context_aware_fallback_to_generic(self, engine):
        """When no context-specific calibration exists, use generic."""
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding", True, quality=0.9,
            )

        engine.update_from_outcomes("forge", "coding")

        adj = engine.get_adjustment("forge", "coding",
                                    language="rust", framework="actix")
        assert adj != 0.0
        generic_adj = engine.get_adjustment("forge", "coding")
        assert adj == generic_adj

    def test_context_aware_framework_specificity(self, engine):
        """Python+FastAPI gets a different calibration than Python+Django."""
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding", True, quality=0.98,
                language="python", framework="fastapi",
            )
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding", True, quality=0.70,
                language="python", framework="django",
            )

        engine.update_from_outcomes("forge", "coding")

        fa_adj = engine.get_adjustment("forge", "coding",
                                        language="python", framework="fastapi")
        dj_adj = engine.get_adjustment("forge", "coding",
                                        language="python", framework="django")
        assert fa_adj > dj_adj

    def test_update_from_outcomes_for_context_specific(self, engine):
        """Should only update the matching context."""
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding",
                              True, quality=0.9, language="python")
        for _ in range(5):
            self._add_outcome(engine._store, "forge", "coding",
                              False, quality=0.2, language="javascript")

        # Only recompute python context
        entry = engine.update_from_outcomes_for_context(
            "forge", "coding", language="python",
        )
        assert entry is not None
        assert entry.adjustment > 0
        assert entry.language == "python"

        # JS should not have been computed yet
        js_adj = engine.get_adjustment("forge", "coding",
                                        language="javascript")
        assert js_adj == 0.0

    def test_update_from_outcomes_for_context_no_match(self, engine):
        """When no outcomes match the context, returns None."""
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding", True, quality=0.9,
                language="python",
            )
        result = engine.update_from_outcomes_for_context(
            "forge", "coding", language="rust",
        )
        assert result is None

    def test_context_calibration_persists_across_sessions(self, engine):
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding", True, quality=0.9,
                language="python",
            )
        engine.update_from_outcomes("forge", "coding")

        # Read back from a fresh engine with the same store
        adj1 = engine.get_adjustment("forge", "coding",
                                     language="python")
        assert adj1 > 0

        cal_entries = engine._store.get_all_calibrations()
        context_entries = [c for c in cal_entries if c.language == "python"]
        assert len(context_entries) >= 1

    def test_update_from_outcomes_returns_count(self, engine):
        """update_from_outcomes now returns number of context groups updated."""
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding", True, quality=0.9,
                language="python",
            )
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding", True, quality=0.85,
                language="javascript",
            )

        count = engine.update_from_outcomes("forge", "coding")
        # At least 2 context groups (python, javascript) + generic
        assert count >= 2

    # ── Time-decay tests ──────────────────────────────────────────

    def test_time_decay_recent_outcomes_dominate(self, engine):
        """Recent good outcomes should outweigh old bad outcomes."""
        import time
        old = time.time() - (200 * 86400)  # 200 days ago
        now = time.time()

        # Old bad outcomes
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding",
                success=False, quality=0.1, timestamp=old,
            )
        # Recent good outcomes
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding",
                success=True, quality=0.95, timestamp=now,
            )

        engine.update_from_outcomes("forge", "coding")
        adj = engine.get_adjustment("forge", "coding")
        assert adj > 0, "Recent good outcomes should outweigh old bad ones"

    def test_time_decay_very_old_outcomes_filtered(self, engine):
        """Outcomes older than maximum_history_days should be excluded."""
        import time
        very_old = time.time() - (400 * 86400)  # 400 days ago

        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding",
                success=True, quality=0.95, timestamp=very_old,
            )

        result = engine.update_from_outcomes_for_context(
            "forge", "coding",
            language="", framework="", project_size="",
        )
        # With only very old outcomes, effective_n should be 0 -> returns None
        assert result is None

    def test_time_decay_neutral_recent_mixed_old(self, engine):
        """Mixed recent bad and old good should produce negative adjustment
        since recent outcomes have higher weight."""
        import time
        old = time.time() - (200 * 86400)
        now = time.time()

        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding",
                success=True, quality=0.95, timestamp=old,
            )
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding",
                success=False, quality=0.1, timestamp=now,
            )

        engine.update_from_outcomes("forge", "coding")
        adj = engine.get_adjustment("forge", "coding")
        assert adj < 0, "Recent bad outcomes should outweigh old good ones"

    def test_query_time_confidence_decay(self, engine):
        """Confidence should decay as calibration ages."""
        import time
        now = time.time()
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding",
                success=True, quality=0.9, timestamp=now,
            )

        engine.update_from_outcomes("forge", "coding")
        adj, conf_fresh = engine.get_adjustment_with_confidence("forge", "coding")
        assert conf_fresh == pytest.approx(0.1, abs=1e-3), "5/50 evidence = 0.1 confidence"

        # Manually age the calibration entry by 150 days
        entries = engine._store.get_all_calibrations()
        for e in entries:
            e.last_updated = now - (150 * 86400)
            engine._store.save_calibration(e)

        adj, conf_aged = engine.get_adjustment_with_confidence("forge", "coding")
        assert conf_aged < conf_fresh, "Aged calibration should have lower confidence"

    def test_query_time_confidence_fully_decayed(self, engine):
        """After enough time, confidence should drop to near zero."""
        import time
        now = time.time()
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding",
                success=True, quality=0.9, timestamp=now,
            )

        engine.update_from_outcomes("forge", "coding")

        # Age the calibration by 1000 days
        entries = engine._store.get_all_calibrations()
        for e in entries:
            e.last_updated = now - (1000 * 86400)
            engine._store.save_calibration(e)

        adj = engine.get_adjustment("forge", "coding")
        assert adj == 0.0, "Fully decayed calibration should return 0 adjustment"

    def test_calibration_config_custom_half_life(self, engine):
        """Using a shorter half-life should make old outcomes decay faster."""
        from core.providers.feedback.models import CalibrationConfig
        import time
        now = time.time()
        old = time.time() - (50 * 86400)

        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding",
                success=False, quality=0.1, timestamp=old,
            )
        for _ in range(5):
            self._add_outcome(
                engine._store, "forge", "coding",
                success=True, quality=0.95, timestamp=now,
            )

        # With default 100-day half-life
        engine.update_from_outcomes("forge", "coding")
        adj_default = engine.get_adjustment("forge", "coding")

        # With 10-day half-life (old outcomes decay much faster)
        short_cfg = CalibrationConfig(half_life_days=10.0)
        short_engine = CalibrationEngine(
            store=engine._store, config=short_cfg,
        )
        short_engine.update_from_outcomes("forge", "coding", force=True)
        adj_short = short_engine.get_adjustment("forge", "coding")

        # Shorter half-life = old bad outcomes decay more = more positive
        assert adj_short >= adj_default, (
            "Shorter half-life should give more weight to recent outcomes"
        )


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
        import time
        from core.providers.feedback.store import FeedbackStore
        from core.providers.feedback.calibrator import CalibrationEngine
        from core.providers.router import ProviderRouter
        from core.providers.registry import provider_registry
        forge = provider_registry.get("forge")
        if forge is None:
            return
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_calibration.db")
            fb_store = FeedbackStore(db_path=db_path)
            cal_engine = CalibrationEngine(store=fb_store)
            router = ProviderRouter(calibration_engine=cal_engine)
            score_before = router._score(forge, {"capability": "coding"})
            now = time.time()
            for _ in range(5):
                d = RoutingDecision(capability="coding", selected_provider="forge", timestamp=now)
                fb_store.save_decision(d)
                fb_store.save_outcome(RoutingOutcome(
                    decision_id=d.decision_id, success=True,
                    quality_score=0.95, duration_ms=100, timestamp=now,
                ))
            cal_engine.update_from_outcomes("forge", "coding")
            score_after = router._score(forge, {"capability": "coding"})
            assert score_after != score_before
            fb_store.close()

    def test_router_score_context_aware(self):
        import time
        from core.providers.feedback.store import FeedbackStore
        from core.providers.feedback.calibrator import CalibrationEngine
        from core.providers.router import ProviderRouter
        from core.providers.registry import provider_registry
        forge = provider_registry.get("forge")
        if forge is None:
            return
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_context.db")
            fb_store = FeedbackStore(db_path=db_path)
            cal_engine = CalibrationEngine(store=fb_store)
            router = ProviderRouter(calibration_engine=cal_engine)
            now = time.time()
            # Python good outcomes
            for _ in range(5):
                d = RoutingDecision(
                    capability="coding", selected_provider="forge",
                    task={"language": "python", "goal": "test"},
                    timestamp=now,
                )
                fb_store.save_decision(d)
                fb_store.save_outcome(RoutingOutcome(
                    decision_id=d.decision_id, success=True,
                    quality_score=0.95, duration_ms=100, timestamp=now,
                ))
            # JS bad outcomes
            for _ in range(5):
                d = RoutingDecision(
                    capability="coding", selected_provider="forge",
                    task={"language": "javascript", "goal": "test"},
                    timestamp=now,
                )
                fb_store.save_decision(d)
                fb_store.save_outcome(RoutingOutcome(
                    decision_id=d.decision_id, success=False,
                    quality_score=0.2, duration_ms=5000, timestamp=now,
                ))
            cal_engine.update_from_outcomes("forge", "coding")

            py_score = router._score(forge, {
                "capability": "coding", "language": "python",
            })
            js_score = router._score(forge, {
                "capability": "coding", "language": "javascript",
            })
            assert py_score > js_score
            fb_store.close()

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

        forge = provider_registry.get("forge")
        if forge is None:
            return

        planner = OrchestrationPlanner()
        plan = planner.plan("Write a function")
        found = False
        for step in plan.steps:
            if "_decision_id" in step.task:
                found = True
                assert step.task["_decision_id"].startswith("dec_")
        assert found, "At least one step should have a decision_id"


# ═════════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═════════════════════════════════════════════════════════════════════════════

class TestFeedbackEdgeCases:
    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_edge.db")
            s = FeedbackStore(db_path=db_path)
            yield s
            s.close()

    def test_decision_with_empty_task_context(self, store):
        d = RoutingDecision(
            capability="coding",
            task={},
            selected_provider="forge",
        )
        store.save_decision(d)
        loaded = store.get_decision(d.decision_id)
        assert loaded.task == {}

    def test_calibration_fallback_all_empty_context(self, store):
        """Fallback chain should handle all-empty context correctly."""
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.05,
        ))
        result = store.get_calibration_fallback(
            "forge", "coding",
            language="", framework="", project_size="",
        )
        assert result is not None
        assert result.adjustment == 0.05

    def test_calibration_fallback_no_context_match(self, store):
        """When no calibration exists at any level, return None."""
        result = store.get_calibration_fallback(
            "forge", "unknown_capability",
            language="python",
        )
        assert result is None

    def test_calibration_summary_includes_context(self, store):
        store.save_calibration(CalibrationEntry(
            provider_id="forge", capability="coding",
            adjustment=0.05, language="python", framework="fastapi",
        ))
        summary = store.get_calibration_summary()
        assert len(summary) == 1
        assert summary[0]["language"] == "python"
        assert summary[0]["framework"] == "fastapi"

    def test_context_key_with_partial_values(self):
        k1 = context_key("coding", "python")
        assert k1 == ("coding", "python", "", "")

        k2 = context_key("testing", "", "jest")
        assert k2 == ("testing", "", "jest", "")


class TestFeedbackLoopIntegration:
    """RC2 integration: pipeline record → ProviderMemory → Router lookup → scoring.

    Verifies the complete loop that was broken by the fallback chain gap.
    """

    TEST_PID = "test_feedback_loop_provider"

    def _cleanup(self):
        """Remove any test keys left in the shared singleton."""
        to_delete = [k for k in provider_memory._records if k[0] == self.TEST_PID]
        for k in to_delete:
            del provider_memory._records[k]

    def test_pipeline_record_router_retrieve(self):
        """Pipeline records feedback (tt=''), Router retrieves it (tt='agent')."""
        self._cleanup()

        # Phase 1: Pipeline records execution feedback with model but no task_type
        provider_memory.record(_ProviderResult(
            provider_id=self.TEST_PID,
            capability="coding",
            success=True,
            duration_ms=1200.0,
            tokens=450,
            metrics={"model": "test_model_v2", "mode": "agent", "rounds": 3},
        ))

        # Phase 2: Router looks up with task_type + model populated
        rec = provider_memory.get_distribution(
            self.TEST_PID, "coding", "agent", "test_model_v2",
        )
        assert rec is not None, "Evidence should be retrievable via fallback chain"
        assert rec.executions >= 1, f"Expected >=1 executions, got {rec.executions}"
        assert rec.successes == 1, f"Expected 1 success, got {rec.successes}"

        # Phase 3: Score reflects evidence (10th percentile lower bound of Beta(2,1))
        score = provider_memory.get_performance_score(
            self.TEST_PID,
            {"capability": "coding", "task_type": "agent", "model": "test_model_v2"},
        )
        # Beta(2,1) lower bound at p=0.10 ≈ 0.365 — distinct from prior 0.5
        assert score > 0.30, f"Expected score >0.30 for 1/1 evidence, got {score}"

        # Phase 4: Confidence reflects evidence
        conf = provider_memory.get_confidence(
            self.TEST_PID, "coding", "agent", "test_model_v2",
        )
        assert conf > 0, f"Expected confidence >0 after evidence, got {conf}"

        self._cleanup()

    def test_no_evidence_returns_prior(self):
        """Without evidence, score = 0.5 (uniform prior)."""
        self._cleanup()

        score = provider_memory.get_performance_score(
            "nonexistent_provider",
            {"capability": "coding", "task_type": "agent", "model": "any"},
        )
        assert score == 0.5, f"Expected prior 0.5, got {score}"

    def test_legacy_record_still_retrievable(self):
        """Backward compat: record_execution still reachable via fallback."""
        self._cleanup()

        provider_memory.record_execution(
            provider_id=self.TEST_PID,
            success=True, duration_ms=500.0,
            capability="coding",
        )

        # Router lookup with model
        rec = provider_memory.get_distribution(
            self.TEST_PID, "coding", "", "qwen2.5:7b",
        )
        assert rec is not None, "Legacy evidence should be retrievable via fallback"
        assert rec.executions >= 1, f"Expected >=1 executions, got {rec.executions}"

        self._cleanup()
