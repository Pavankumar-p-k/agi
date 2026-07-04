"""Tests for core/decision/ — unified decision engine."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.decision.evidence import DecisionEvidence
from core.decision.models import CandidateEvidence, DecisionResult, EvidenceDimension, UnifiedScore
from core.decision.scoring import DecisionTrace, UnifiedDecisionModel
from core.workflow.calibration import WorkflowCalibrationEngine, WorkflowPrediction


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def sample_dimensions():
    return [
        EvidenceDimension(name="workflow_success", score=0.8, weight=0.25,
                          reason="Workflow success: 80% (evidence: 10)",
                          confidence=0.9, source="workflow_calibration"),
        EvidenceDimension(name="provider_quality", score=0.7, weight=0.20,
                          reason="Provider quality: 70% across 3 capabilities",
                          confidence=0.8, source="provider_calibration"),
        EvidenceDimension(name="strategy_alignment", score=0.6, weight=0.15,
                          reason="Strategy success: 60% risk: 20%",
                          confidence=0.5, source="strategy"),
        EvidenceDimension(name="system_health", score=1.0, weight=0.10,
                          reason="All systems healthy",
                          confidence=1.0, source="health"),
        EvidenceDimension(name="budget_viability", score=1.0, weight=0.10,
                          reason="Within budget",
                          confidence=1.0, source="budget"),
        EvidenceDimension(name="context_fit", score=0.8, weight=0.10,
                          reason="Context match at 'task+lang' level",
                          confidence=0.8, source="context"),
        EvidenceDimension(name="confidence", score=0.85, weight=0.10,
                          reason="Aggregated confidence: 85%",
                          confidence=0.85, source="aggregated"),
    ]


@pytest.fixture
def sample_evidence(sample_dimensions):
    return CandidateEvidence(template_id="test_workflow", template_version=1,
                             dimensions=list(sample_dimensions))


@pytest.fixture
def evidence_for_second():
    """Slightly lower-scored evidence for a second candidate."""
    return CandidateEvidence(template_id="test_workflow_v2", template_version=1,
                             dimensions=[
                                 EvidenceDimension(name="workflow_success", score=0.5, weight=0.25,
                                                   reason="Workflow success: 50%",
                                                   confidence=0.6, source="workflow_calibration"),
                                 EvidenceDimension(name="provider_quality", score=0.6, weight=0.20,
                                                   reason="Provider quality: 60%",
                                                   confidence=0.5, source="provider_calibration"),
                                 EvidenceDimension(name="strategy_alignment", score=0.5, weight=0.15,
                                                   reason="Strategy success: 50%",
                                                   confidence=0.4, source="strategy"),
                                 EvidenceDimension(name="system_health", score=1.0, weight=0.10,
                                                   reason="All systems healthy",
                                                   confidence=1.0, source="health"),
                                 EvidenceDimension(name="budget_viability", score=1.0, weight=0.10,
                                                   reason="Within budget",
                                                   confidence=1.0, source="budget"),
                                 EvidenceDimension(name="context_fit", score=0.5, weight=0.10,
                                                   reason="Context match at 'generic' level",
                                                   confidence=0.5, source="context"),
                                 EvidenceDimension(name="confidence", score=0.6, weight=0.10,
                                                   reason="Aggregated confidence: 60%",
                                                   confidence=0.6, source="aggregated"),
                             ])


# ── Model Tests ─────────────────────────────────────────────────────


class TestEvidenceDimension:
    def test_defaults(self):
        d = EvidenceDimension(name="test")
        assert d.score == 0.0
        assert d.weight == 0.0
        assert d.reason == ""
        assert d.confidence == 0.0
        assert d.source == ""


class TestCandidateEvidence:
    def test_defaults(self):
        c = CandidateEvidence()
        assert c.template_id == ""
        assert c.template_version == 1
        assert c.dimensions == []
        assert c.fingerprint_key == ""

    def test_with_dimensions(self, sample_dimensions):
        c = CandidateEvidence(template_id="t1", template_version=2,
                              dimensions=list(sample_dimensions))
        assert c.template_id == "t1"
        assert c.template_version == 2
        assert len(c.dimensions) == 7


class TestUnifiedScore:
    def test_defaults(self):
        s = UnifiedScore()
        assert s.final_score == 0.0
        assert s.reasons == []
        assert s.concerns == []

    def test_with_values(self, sample_dimensions):
        s = UnifiedScore(template_id="t1", final_score=0.85,
                         dimensions=list(sample_dimensions),
                         reasons=["✓ Good"], concerns=["✗ Expensive"])
        assert s.final_score == 0.85
        assert len(s.reasons) == 1
        assert len(s.concerns) == 1


class TestDecisionResult:
    def test_defaults(self):
        r = DecisionResult()
        assert r.selected is None
        assert r.alternatives == []
        assert r.total_candidates == 0

    def test_with_selected(self, sample_dimensions):
        s = UnifiedScore(template_id="t1", final_score=0.85,
                         dimensions=list(sample_dimensions))
        r = DecisionResult(selected=s, total_candidates=1)
        assert r.selected is not None
        assert r.selected.template_id == "t1"
        assert r.total_candidates == 1

    def test_with_alternatives(self, sample_dimensions):
        s1 = UnifiedScore(template_id="t1", final_score=0.85,
                          dimensions=list(sample_dimensions))
        s2 = UnifiedScore(template_id="t2", final_score=0.50)
        r = DecisionResult(selected=s1, alternatives=[s2], total_candidates=2)
        assert len(r.alternatives) == 1


# ── Scoring Tests ───────────────────────────────────────────────────


class TestUnifiedDecisionModel:
    def test_score_basic(self, sample_evidence):
        model = UnifiedDecisionModel()
        result = model.score(sample_evidence)
        assert isinstance(result, UnifiedScore)
        assert result.template_id == "test_workflow"
        assert result.final_score > 0
        assert result.final_score <= 1.0
        assert len(result.dimensions) == 7
        assert len(result.reasons) > 0
        assert result.confidence > 0
        assert result.elapsed_ms >= 0

    def test_score_empty_dimensions(self):
        model = UnifiedDecisionModel()
        evidence = CandidateEvidence(template_id="empty", dimensions=[])
        result = model.score(evidence)
        assert result.final_score == 0.0
        assert result.confidence == 0.0

    def test_score_zero_weight_dimensions(self):
        """Dimensions with weight=0 should be excluded from the score."""
        model = UnifiedDecisionModel()
        evidence = CandidateEvidence(template_id="zero_weights", dimensions=[
            EvidenceDimension(name="unused", score=1.0, weight=0.0,
                              reason="Not used", confidence=1.0),
        ])
        result = model.score(evidence)
        # No effective weight → score is 0
        assert result.final_score == 0.0

    def test_rank_selects_highest(self, sample_evidence, evidence_for_second):
        model = UnifiedDecisionModel()
        result = model.rank([evidence_for_second, sample_evidence])
        assert result.selected is not None
        assert result.selected.template_id == "test_workflow"
        assert result.total_candidates == 2
        assert len(result.alternatives) == 1

    def test_rank_single_candidate(self, sample_evidence):
        model = UnifiedDecisionModel()
        result = model.rank([sample_evidence])
        assert result.selected is not None
        assert result.selected.template_id == "test_workflow"
        assert result.alternatives == []

    def test_rank_no_candidates(self):
        model = UnifiedDecisionModel()
        result = model.rank([])
        assert result.selected is None
        assert result.total_candidates == 0

    def test_score_clamping(self):
        """Scores outside [0, 1] should be clamped."""
        model = UnifiedDecisionModel()
        evidence = CandidateEvidence(template_id="clamp", dimensions=[
            EvidenceDimension(name="negative", score=-0.5, weight=1.0,
                              reason="Negative", confidence=1.0, source="test"),
        ])
        # All weight goes to negative
        result = model.score(evidence)
        assert result.final_score == 0.0  # clamped


# ── DecisionTrace Tests ─────────────────────────────────────────────


class TestDecisionTrace:
    def test_format_no_selection(self):
        result = DecisionResult()
        text = DecisionTrace.format(result)
        assert "No candidates available" in text

    def test_format_with_selection(self, sample_dimensions):
        score = UnifiedScore(template_id="t1", final_score=0.85,
                             dimensions=list(sample_dimensions),
                             reasons=["✓ Good reason"], concerns=["✗ Concern"])
        result = DecisionResult(selected=score, total_candidates=1)
        text = DecisionTrace.format(result)
        assert "Selected: t1" in text
        assert "Good reason" in text
        assert "Concern" in text

    def test_format_with_alternatives(self, sample_dimensions):
        s1 = UnifiedScore(template_id="t1", final_score=0.85,
                          dimensions=list(sample_dimensions),
                          reasons=["✓ Best candidate"])
        s2 = UnifiedScore(template_id="t2", final_score=0.50,
                          dimensions=list(sample_dimensions),
                          reasons=["✓ Second best"])
        result = DecisionResult(selected=s1, alternatives=[s2], total_candidates=2)
        text = DecisionTrace.format(result)
        assert "Rejected:" in text
        assert "t1" in text
        assert "t2" in text

    def test_format_dimensions(self, sample_dimensions):
        score = UnifiedScore(template_id="t1", final_score=0.85,
                             dimensions=list(sample_dimensions))
        text = DecisionTrace.format_dimensions(score)
        assert "Dimensions for t1" in text
        assert "workflow_success" in text
        assert "FINAL" in text


# ── DecisionEvidence Tests ──────────────────────────────────────────


class TestDecisionEvidence:
    def test_collect_no_systems(self):
        """When no systems are wired, all dimensions should have defaults."""
        collector = DecisionEvidence()
        results = collector.collect([("t1", 1)], task_type="build")
        assert len(results) == 1
        assert results[0].template_id == "t1"
        assert len(results[0].dimensions) == 7
        # All should have score=0 or sensible defaults
        dims = {d.name: d for d in results[0].dimensions}
        assert "workflow_success" in dims
        assert "provider_quality" in dims
        assert "system_health" in dims
        assert dims["system_health"].score == 1.0  # OK default

    def test_collect_multiple_templates(self):
        collector = DecisionEvidence()
        results = collector.collect([("t1", 1), ("t2", 2), ("t3", 1)])
        assert len(results) == 3
        assert results[0].template_id == "t1"
        assert results[1].template_id == "t2"
        assert results[2].template_id == "t3"

    def test_collect_different_timestamps(self):
        """Each collect should have a unique timestamp."""
        import time
        collector = DecisionEvidence()
        r1 = collector.collect([("t1", 1)])
        time.sleep(0.01)
        r2 = collector.collect([("t1", 1)])
        assert r1[0].collected_at < r2[0].collected_at

    def test_collect_with_workflow_calibration(self):
        """Wired WorkflowCalibrationEngine should produce meaningful scores."""
        wf_cal = MagicMock(spec=WorkflowCalibrationEngine)
        wf_cal.predict.return_value = WorkflowPrediction(
            expected_success=0.85,
            confidence=0.9,
            evidence_count=15,
        )
        collector = DecisionEvidence(workflow_calibration=wf_cal)
        results = collector.collect([("t1", 1)], task_type="build",
                                     languages="python", frameworks="pytest",
                                     project_size="medium")
        assert len(results) == 1
        dims = {d.name: d for d in results[0].dimensions}
        wf = dims["workflow_success"]
        assert wf.score > 0
        assert wf.confidence > 0
        assert "Workflow success: 85%" in wf.reason
        assert wf.source == "workflow_calibration"

    def test_collect_provider_capabilities(self):
        """When capabilities are provided, provider dimension should be populated."""
        prov_cal = MagicMock()
        prov_cal.get_adjustment_with_confidence.return_value = (0.2, 0.8)
        collector = DecisionEvidence(provider_calibration=prov_cal)
        results = collector.collect([("t1", 1)],
                                     capabilities=["build", "test", "deploy"])
        dims = {d.name: d for d in results[0].dimensions}
        prov = dims["provider_quality"]
        assert prov.score > 0.5
        assert "Provider quality" in prov.reason

    def test_collect_workflow_calibration_error(self):
        """A failing calibration should not crash the collector."""
        wf_cal = MagicMock(spec=WorkflowCalibrationEngine)
        wf_cal.predict.side_effect = RuntimeError("Calibration failed")
        collector = DecisionEvidence(workflow_calibration=wf_cal)
        results = collector.collect([("t1", 1)])
        dims = {d.name: d for d in results[0].dimensions}
        wf = dims["workflow_success"]
        assert wf.score == 0.0
        assert "error" in wf.reason.lower()

    def test_collect_strategy(self):
        """Wired strategy predictor should produce strategy_alignment."""
        from core.strategy.v2.models import StrategyCandidate

        strat_pred = MagicMock()
        strat_pred.predict.return_value = StrategyCandidate(
            strategy_id="test", name="test", description="test",
            proposal_ids=[], impact_by_dimension={"build": 0.75},
            overall_improvement=0.75, risk=0.15, implementation_cost=0.2,
            confidence=0.8,
        )
        collector = DecisionEvidence(strategy_predictor=strat_pred)
        results = collector.collect([("t1", 1)], task_type="build")
        dims = {d.name: d for d in results[0].dimensions}
        strat = dims["strategy_alignment"]
        assert strat.score > 0.5
        assert "Strategy improvement: 75%" in strat.reason

    def test_collect_health_default(self):
        """Without health monitor, system_health defaults to 1.0."""
        collector = DecisionEvidence()
        results = collector.collect([("t1", 1)])
        dims = {d.name: d for d in results[0].dimensions}
        assert dims["system_health"].score == 1.0

    def test_collect_health_ok(self):
        """Health monitor returning ok → score=1.0."""
        health = MagicMock()
        health.all_ok.return_value = True
        collector = DecisionEvidence(health_monitor=health)
        results = collector.collect([("t1", 1)])
        dims = {d.name: d for d in results[0].dimensions}
        assert dims["system_health"].score == 1.0

    def test_collect_health_unhealthy(self):
        """Health monitor returning not ok → score=0.5."""
        health = MagicMock()
        health.all_ok.return_value = False
        collector = DecisionEvidence(health_monitor=health)
        results = collector.collect([("t1", 1)])
        dims = {d.name: d for d in results[0].dimensions}
        assert dims["system_health"].score == 0.5

    def test_collect_budget_default(self):
        """Without budget manager, budget_viability defaults to 1.0."""
        collector = DecisionEvidence()
        results = collector.collect([("t1", 1)])
        dims = {d.name: d for d in results[0].dimensions}
        assert dims["budget_viability"].score == 1.0

    def test_collect_budget_exceeded(self):
        """Budget manager reporting exceeded → score=0.3."""
        budget = MagicMock()
        budget.all_ok.return_value = (False, "Budget limit exceeded")
        collector = DecisionEvidence(budget_manager=budget)
        results = collector.collect([("t1", 1)])
        dims = {d.name: d for d in results[0].dimensions}
        assert dims["budget_viability"].score == 0.3

    def test_collect_context_fit_no_calibration(self):
        """Without calibration, context_fit defaults to 0.5."""
        collector = DecisionEvidence()
        results = collector.collect([("t1", 1)])
        dims = {d.name: d for d in results[0].dimensions}
        assert dims["context_fit"].score == 0.5

    def test_collect_confidence_critical_missing(self):
        """Missing critical dimensions should reduce confidence score."""
        wf_cal = MagicMock(spec=WorkflowCalibrationEngine)
        wf_cal.predict.side_effect = RuntimeError("Missing")
        collector = DecisionEvidence(workflow_calibration=wf_cal)
        results = collector.collect([("t1", 1)], capabilities=["build"])
        dims = {d.name: d for d in results[0].dimensions}
        conf = dims["confidence"]
        # workflow_success and possibly provider_quality missing
        # → penalty reduces confidence below 0.5
        assert conf.score <= 0.5


# ── StrategyBridge Tests ────────────────────────────────────────────


class TestStrategyBridge:
    def test_dimension_without_components(self):
        """Without wired components, should return sensible defaults."""
        from core.decision.bridge import StrategyBridge
        bridge = StrategyBridge()
        from core.strategy.v2.models import StrategyCandidate
        candidate = StrategyCandidate(
            strategy_id="test", name="test", description="test",
            proposal_ids=[], impact_by_dimension={},
            overall_improvement=0.5, risk=0.3, implementation_cost=0.3,
            confidence=0.5,
        )
        dim = bridge.dimension_for_strategy(candidate)
        assert dim.name == "strategy_alignment"
        assert dim.score == 0.25  # 0.5 * 0.5 = 0.25
        assert dim.confidence == 0.5

    def test_dimension_with_predictor(self):
        """Wired predictor should produce meaningful score."""
        from core.decision.bridge import StrategyBridge
        from core.strategy.v2.models import StrategyCandidate

        predictor = MagicMock()
        predictor.predict.return_value = StrategyCandidate(
            strategy_id="test", name="test", description="test",
            proposal_ids=[], impact_by_dimension={},
            overall_improvement=0.85, risk=0.10, implementation_cost=0.3,
            confidence=0.9,
        )
        bridge = StrategyBridge(predictor=predictor)
        candidate = StrategyCandidate(
            strategy_id="test", name="test", description="test",
            proposal_ids=[], impact_by_dimension={},
            overall_improvement=0.5, risk=0.3, implementation_cost=0.3,
            confidence=0.5,
        )
        dim = bridge.dimension_for_strategy(candidate)
        assert dim.score == 0.85 * 0.9
        assert dim.confidence == 0.9
        assert "Improvement: 85%" in dim.reason

    def test_tradeoff_insufficient_candidates(self):
        """With fewer than 2 candidates, tradeoff returns default."""
        from core.decision.bridge import StrategyBridge
        from core.strategy.v2.models import StrategyCandidate
        bridge = StrategyBridge()
        dim = bridge.dimension_for_tradeoff([])
        assert dim.name == "tradeoff_fitness"
        assert dim.score == 0.5
        assert "insufficient" in dim.reason

    def test_tradeoff_with_wired_engine(self):
        """With TradeoffEngine wired, should produce meaningful score."""
        from core.decision.bridge import StrategyBridge
        from core.strategy.v2.models import StrategyCandidate
        from core.strategy.v2.tradeoffs import TradeoffEngine

        engine = TradeoffEngine()
        bridge = StrategyBridge(tradeoff_engine=engine)
        c1 = StrategyCandidate(
            strategy_id="a", name="A", description="Good candidate",
            proposal_ids=[], impact_by_dimension={"build": 0.8},
            overall_improvement=0.8, risk=0.1, implementation_cost=0.2,
            confidence=0.9,
        )
        c2 = StrategyCandidate(
            strategy_id="b", name="B", description="Weak candidate",
            proposal_ids=[], impact_by_dimension={"build": 0.2},
            overall_improvement=0.2, risk=0.6, implementation_cost=0.7,
            confidence=0.3,
        )
        dim = bridge.dimension_for_tradeoff([c1, c2])
        assert dim.name == "tradeoff_fitness"
        assert dim.score > 0.5  # c1 should score higher

    def test_rank_templates_no_selector(self):
        """Without selector, all templates get 0.5."""
        from core.decision.bridge import StrategyBridge
        bridge = StrategyBridge()
        results = bridge.rank_templates(["t1", "t2"], {})
        assert len(results) == 2
        assert all(r[1] == 0.5 for r in results)
