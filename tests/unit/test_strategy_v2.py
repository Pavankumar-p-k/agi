"""Phase 15.1–15.2 tests — Strategic Reasoning Layer.

Tests cover all 9 files in core/strategy_v2/:
  models, planner, predictor, tradeoffs, evaluator, selector,
  memory_adapter, executor, portfolio
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest import TestCase


# ── Models ───────────────────────────────────────────────────────


class TestStrategyModels(TestCase):
    def test_01_strategy_candidate_creation(self):
        from core.strategy_v2.models import StrategyCandidate, TimeHorizon
        sc = StrategyCandidate(
            strategy_id="strat_001",
            name="Add verification to browser_tool",
            description="verification_builtin improves success by 33%",
            proposal_ids=["prp_001"],
            impact_by_dimension={"browser": 0.33, "general": 0.03},
            overall_improvement=0.30,
            risk=0.10,
            implementation_cost=0.40,
            confidence=0.89,
            time_horizon=TimeHorizon.SHORT_TERM,
        )
        self.assertEqual(sc.strategy_id, "strat_001")
        self.assertEqual(sc.time_horizon, TimeHorizon.SHORT_TERM)

    def test_02_strategy_candidate_to_dict(self):
        from core.strategy_v2.models import StrategyCandidate
        sc = StrategyCandidate(
            strategy_id="strat_001",
            name="Test strategy",
            description="Description",
            proposal_ids=["prp_001"],
            impact_by_dimension={"browser": 0.30},
            overall_improvement=0.30,
            risk=0.10,
            implementation_cost=0.40,
            confidence=0.89,
        )
        d = sc.to_dict()
        self.assertEqual(d["strategy_id"], "strat_001")
        self.assertEqual(d["risk"], 0.1)
        self.assertEqual(d["proposal_ids"], ["prp_001"])

    def test_03_strategic_decision_creation(self):
        from core.strategy_v2.models import StrategicDecision, StrategyStatus
        sd = StrategicDecision(
            decision_id="dec_001",
            chosen_strategy_id="strat_001",
            alternative_strategy_ids=["strat_002", "strat_003"],
            rationale="strat_001 has highest utility",
            utility_scores={"strat_001": 0.45, "strat_002": 0.30},
        )
        self.assertEqual(sd.status, StrategyStatus.SELECTED)
        self.assertEqual(len(sd.alternative_strategy_ids), 2)

    def test_04_tradeoff_analysis_creation(self):
        from core.strategy_v2.models import TradeoffAnalysis
        ta = TradeoffAnalysis(
            strategy_id="strat_001",
            net_utility=0.42,
            dimension_scores={"improvement": 0.15, "risk": -0.05},
            strengths=["improvement", "low_cost"],
            weaknesses=["long_term"],
        )
        self.assertEqual(ta.net_utility, 0.42)
        self.assertIn("improvement", ta.strengths)

    def test_05_enums(self):
        from core.strategy_v2.models import (
            ImpactDimension, StrategyStatus, TimeHorizon,
        )
        self.assertEqual(TimeHorizon.SHORT_TERM.value, "short_term")
        self.assertEqual(StrategyStatus.CANDIDATE.value, "candidate")
        self.assertEqual(ImpactDimension.CODING.value, "coding")


# ── Planner ──────────────────────────────────────────────────────


class TestStrategicPlanner(TestCase):
    def _make_proposal(self, proposal_id: str, target_system: str = "browser_tool",
                        proposal_type: str = "add_capability",
                        expected_improvement: float = 0.33,
                        confidence: float = 0.89,
                        status: str = "approved"):
        from core.generalization.models import ImprovementProposal, ProposalStatus
        return ImprovementProposal(
            proposal_id=proposal_id,
            target_system=target_system,
            proposal_type=proposal_type,
            principle_id="pr_001",
            title=f"Test {proposal_id}",
            rationale="Rationale",
            expected_improvement=expected_improvement,
            confidence=confidence,
            status=ProposalStatus(status),
        )

    def test_10_single_proposal_creates_one_strategy(self):
        from core.strategy_v2.planner import StrategicPlanner
        planner = StrategicPlanner()
        proposals = [self._make_proposal("prp_001")]
        candidates = planner.plan_from_proposals(proposals)
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(len(c.proposal_ids), 1)
        self.assertAlmostEqual(c.overall_improvement, 0.33 * 0.89)

    def test_11_multiple_proposals_create_multiple_strategies(self):
        from core.strategy_v2.planner import StrategicPlanner
        planner = StrategicPlanner()
        proposals = [
            self._make_proposal("prp_001", "tool_a"),
            self._make_proposal("prp_002", "tool_b"),
        ]
        candidates = planner.plan_from_proposals(proposals)
        self.assertEqual(len(candidates), 2)
        self.assertNotEqual(candidates[0].strategy_id, candidates[1].strategy_id)

    def test_12_combined_strategy_for_same_system(self):
        """Two proposals for the same system produce 2 single + 1 combined."""
        from core.strategy_v2.planner import StrategicPlanner
        planner = StrategicPlanner()
        proposals = [
            self._make_proposal("prp_001", "browser_tool", "add_capability"),
            self._make_proposal("prp_002", "browser_tool", "add_capability"),
        ]
        candidates = planner.plan_from_proposals(proposals)
        # 2 single + 1 combined = 3
        self.assertEqual(len(candidates), 3)
        combined = [c for c in candidates if len(c.proposal_ids) == 2]
        self.assertEqual(len(combined), 1)

    def test_13_empty_proposals(self):
        from core.strategy_v2.planner import StrategicPlanner
        planner = StrategicPlanner()
        candidates = planner.plan_from_proposals([])
        self.assertEqual(candidates, [])

    def test_14_candidate_has_impact_dimensions(self):
        """Each candidate has inferred impact dimensions."""
        from core.strategy_v2.planner import StrategicPlanner
        planner = StrategicPlanner()
        proposals = [self._make_proposal("prp_001", "browser_tool")]
        candidates = planner.plan_from_proposals(proposals)
        self.assertGreater(len(candidates[0].impact_by_dimension), 0)
        self.assertIn("browser", candidates[0].impact_by_dimension)

    def test_15_risk_derived_from_confidence(self):
        """Risk = 1 - confidence."""
        from core.strategy_v2.planner import StrategicPlanner
        planner = StrategicPlanner()
        proposals = [self._make_proposal("prp_001", "tool_a", confidence=0.70)]
        candidates = planner.plan_from_proposals(proposals)
        self.assertAlmostEqual(candidates[0].risk, 0.30)

    def test_16_cost_estimated_from_proposal_type(self):
        """add_capability has cost 0.4."""
        from core.strategy_v2.planner import StrategicPlanner
        planner = StrategicPlanner()
        proposals = [self._make_proposal("prp_001")]
        candidates = planner.plan_from_proposals(proposals)
        self.assertAlmostEqual(candidates[0].implementation_cost, 0.40)


# ── Predictor ────────────────────────────────────────────────────


class TestOutcomePredictor(TestCase):
    def _make_candidate(self, improvement: float = 0.30, risk: float = 0.10,
                        cost: float = 0.40, confidence: float = 0.89):
        from core.strategy_v2.models import StrategyCandidate
        return StrategyCandidate(
            strategy_id="strat_pred",
            name="Test",
            description="Test",
            proposal_ids=["prp_001"],
            impact_by_dimension={"general": improvement},
            overall_improvement=improvement,
            risk=risk,
            implementation_cost=cost,
            confidence=confidence,
        )

    def test_20_predicts_short_term_for_low_cost_low_risk(self):
        from core.strategy_v2.predictor import OutcomePredictor
        from core.strategy_v2.models import TimeHorizon
        p = OutcomePredictor()
        c = self._make_candidate(cost=0.2, risk=0.2)
        result = p.predict(c)
        self.assertEqual(result.time_horizon, TimeHorizon.SHORT_TERM)

    def test_21_predicts_long_term_for_high_cost(self):
        from core.strategy_v2.predictor import OutcomePredictor
        from core.strategy_v2.models import TimeHorizon
        p = OutcomePredictor()
        c = self._make_candidate(cost=0.7, risk=0.3)
        result = p.predict(c)
        self.assertEqual(result.time_horizon, TimeHorizon.LONG_TERM)

    def test_22_predicts_long_term_for_high_risk(self):
        from core.strategy_v2.predictor import OutcomePredictor
        from core.strategy_v2.models import TimeHorizon
        p = OutcomePredictor()
        c = self._make_candidate(cost=0.3, risk=0.7)
        result = p.predict(c)
        self.assertEqual(result.time_horizon, TimeHorizon.LONG_TERM)

    def test_23_medium_term_by_default(self):
        from core.strategy_v2.predictor import OutcomePredictor
        from core.strategy_v2.models import TimeHorizon
        p = OutcomePredictor()
        c = self._make_candidate(cost=0.4, risk=0.4)
        result = p.predict(c)
        self.assertEqual(result.time_horizon, TimeHorizon.MEDIUM_TERM)

    def test_24_improvement_range(self):
        from core.strategy_v2.predictor import OutcomePredictor
        p = OutcomePredictor()
        c = self._make_candidate(improvement=0.50, confidence=0.80)
        pessimistic, optimistic = p.estimate_improvement_range(c)
        self.assertLess(pessimistic, optimistic)
        self.assertAlmostEqual(pessimistic, 0.50 - 0.20 * 0.50)


# ── Tradeoff Engine ──────────────────────────────────────────────


class TestTradeoffEngine(TestCase):
    def _make_candidate(self, strategy_id: str, improvement: float = 0.30,
                        risk: float = 0.10, cost: float = 0.40,
                        confidence: float = 0.89, horizon: str = "short_term"):
        from core.strategy_v2.models import StrategyCandidate, TimeHorizon
        return StrategyCandidate(
            strategy_id=strategy_id,
            name=f"Strategy {strategy_id}",
            description="Test",
            proposal_ids=["prp_001"],
            impact_by_dimension={"general": improvement},
            overall_improvement=improvement,
            risk=risk,
            implementation_cost=cost,
            confidence=confidence,
            time_horizon=TimeHorizon(horizon),
        )

    def test_30_higher_improvement_higher_utility(self):
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()
        low = self._make_candidate("low", improvement=0.20)
        high = self._make_candidate("high", improvement=0.60)
        a_low = e.analyze(low)
        a_high = e.analyze(high)
        self.assertGreater(a_high.net_utility, a_low.net_utility)

    def test_31_lower_risk_higher_utility(self):
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()
        risky = self._make_candidate("risky", risk=0.80)
        safe = self._make_candidate("safe", risk=0.10)
        a_risky = e.analyze(risky)
        a_safe = e.analyze(safe)
        self.assertGreater(a_safe.net_utility, a_risky.net_utility)

    def test_32_strengths_identified(self):
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()
        c = self._make_candidate("good", improvement=0.70, risk=0.10,
                                  cost=0.20, confidence=0.95)
        a = e.analyze(c)
        self.assertIn("improvement", a.strengths)
        self.assertIn("low_risk", a.strengths)
        self.assertIn("low_cost", a.strengths)

    def test_33_weaknesses_identified(self):
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()
        c = self._make_candidate("bad", improvement=0.10, risk=0.80,
                                  cost=0.80, confidence=0.30)
        a = e.analyze(c)
        self.assertIn("improvement", a.weaknesses)
        self.assertIn("high_risk", a.weaknesses)

    def test_34_analyze_all_incorporates_opportunity_cost(self):
        """analyze_all should penalize strategies with strong alternatives."""
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()
        c1 = self._make_candidate("s1", improvement=0.50)
        c2 = self._make_candidate("s2", improvement=0.45)
        analyses = e.analyze_all([c1, c2])
        # Both should have opportunity_cost dimension
        for a in analyses:
            self.assertIn("opportunity_cost", a.dimension_scores)

    def test_35_net_utility_structure(self):
        """Net utility = sum of dimension scores."""
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()
        c = self._make_candidate("s1", improvement=0.30, risk=0.10,
                                  cost=0.40, confidence=0.89)
        a = e.analyze(c)
        self.assertAlmostEqual(a.net_utility,
                                sum(a.dimension_scores.values()))

    # ── Future Option Value (Phase 15.2+) ─────────────────────

    def _make_candidate_with_enables(self, sid: str, improvement: float = 0.30,
                                      risk: float = 0.10, cost: float = 0.40,
                                      confidence: float = 0.89,
                                      horizon: str = "short_term",
                                      enabled: list[str] | None = None):
        from core.strategy_v2.models import StrategyCandidate, TimeHorizon
        return StrategyCandidate(
            strategy_id=sid,
            name=f"Strategy {sid}",
            description="Test",
            proposal_ids=["prp_" + sid],
            impact_by_dimension={"general": improvement},
            overall_improvement=improvement,
            risk=risk,
            implementation_cost=cost,
            confidence=confidence,
            time_horizon=TimeHorizon(horizon),
            enabled_strategy_ids=enabled or [],
        )

    def test_36_option_value_added_when_enabled_strategies(self):
        """A strategy that enables others gets option_value > 0."""
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()

        # s1 enables s2, which has its own utility
        s1 = self._make_candidate_with_enables("s1", improvement=0.20,
                                                enabled=["s2"])
        s2 = self._make_candidate_with_enables("s2", improvement=0.40,
                                                horizon="short_term")

        analyses = e.analyze_all([s1, s2])
        analysis_map = {a.strategy_id: a for a in analyses}

        # s2 has no enabled strategies → no option value
        self.assertEqual(analysis_map["s2"].option_value, 0.0)

        # s1 enables s2 → should have option_value > 0
        self.assertGreater(analysis_map["s1"].option_value, 0.0)

    def test_37_option_value_affects_net_utility(self):
        """The option value bonus increases net_utility."""
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()

        s_enabler = self._make_candidate_with_enables("enabler",
            improvement=0.20, cost=0.30, enabled=["future"])
        s_future = self._make_candidate_with_enables("future",
            improvement=0.50, horizon="short_term")

        s_lone = self._make_candidate_with_enables("lone",
            improvement=0.20, cost=0.30)

        analyses = e.analyze_all([s_enabler, s_future, s_lone])
        analysis_map = {a.strategy_id: a for a in analyses}

        # enabler and lone have similar direct utility,
        # but enabler gets an option value bonus
        self.assertGreater(
            analysis_map["enabler"].net_utility,
            analysis_map["lone"].net_utility,
        )

    def test_38_option_value_discounted_by_time_horizon(self):
        """Short-term enabled strategies contribute more option value."""
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()

        s_short = self._make_candidate_with_enables("short",
            improvement=0.20, enabled=["future_short"])
        s_long = self._make_candidate_with_enables("long",
            improvement=0.20, enabled=["future_long"])
        future_short = self._make_candidate_with_enables("future_short",
            improvement=0.40, horizon="short_term")
        future_long = self._make_candidate_with_enables("future_long",
            improvement=0.40, horizon="long_term")

        analyses = e.analyze_all([s_short, s_long, future_short, future_long])
        analysis_map = {a.strategy_id: a for a in analyses}

        # Both enablers have same utility and enable same-utility futures
        # But short-term discount (0.8) > long-term discount (0.2)
        self.assertGreater(
            analysis_map["short"].option_value,
            analysis_map["long"].option_value,
        )

    def test_39_option_value_dimension_in_analysis(self):
        """option_value appears as a dimension score when > 0."""
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()

        s1 = self._make_candidate_with_enables("s1", improvement=0.20,
                                                enabled=["s2"])
        s2 = self._make_candidate_with_enables("s2", improvement=0.40,
                                                horizon="short_term")

        analyses = e.analyze_all([s1, s2])
        analysis = next(a for a in analyses if a.strategy_id == "s1")

        self.assertIn("option_value", analysis.dimension_scores)
        self.assertGreater(analysis.dimension_scores["option_value"], 0)

        # s2 has no enabled strategies → option_value dimension is 0
        analysis2 = next(a for a in analyses if a.strategy_id == "s2")
        self.assertEqual(analysis2.dimension_scores["option_value"], 0.0)

    def test_36b_candidate_serializes_enabled_ids(self):
        """enabled_strategy_ids appears in to_dict()."""
        from core.strategy_v2.models import StrategyCandidate
        c = StrategyCandidate(
            strategy_id="s1", name="T", description="",
            proposal_ids=[], impact_by_dimension={},
            overall_improvement=0.3, risk=0.1,
            implementation_cost=0.4, confidence=0.89,
            enabled_strategy_ids=["s2", "s3"],
        )
        d = c.to_dict()
        self.assertIn("enabled_strategy_ids", d)
        self.assertEqual(d["enabled_strategy_ids"], ["s2", "s3"])

    def test_36c_empty_enabled_ids_produces_no_option_value(self):
        """No enabled_strategy_ids = no option value (backward compatible)."""
        from core.strategy_v2.tradeoffs import TradeoffEngine
        from core.strategy_v2.models import StrategyCandidate, TimeHorizon
        e = TradeoffEngine()
        c = StrategyCandidate(
            strategy_id="solo", name="Solo", description="",
            proposal_ids=[], impact_by_dimension={},
            overall_improvement=0.3, risk=0.1,
            implementation_cost=0.4, confidence=0.89,
        )
        # No enabled_strategy_ids set
        a = e.analyze(c)
        self.assertEqual(a.option_value, 0.0)

    def test_36d_non_existent_enabled_id_skipped_gracefully(self):
        """If enabled_strategy_ids reference a non-existent candidate, skip."""
        from core.strategy_v2.tradeoffs import TradeoffEngine
        e = TradeoffEngine()
        s1 = self._make_candidate_with_enables("s1", enabled=["nonexistent"])
        analyses = e.analyze_all([s1])
        self.assertEqual(analyses[0].option_value, 0.0)

    def test_36e_negative_utility_enabled_strategies_do_not_contribute(self):
        """Only positive-utility enabled strategies add option value."""
        from core.strategy_v2.tradeoffs import TradeoffEngine
        from core.strategy_v2.models import StrategyCandidate, TimeHorizon
        e = TradeoffEngine()
        # s1 enables s2, but s2 has very high risk → negative utility
        s1 = self._make_candidate_with_enables("s1", enabled=["s2"])
        s2 = StrategyCandidate(
            strategy_id="s2", name="Bad", description="",
            proposal_ids=[], impact_by_dimension={},
            overall_improvement=0.0, risk=0.95,  # high risk → negative utility
            implementation_cost=0.5, confidence=0.3,
        )
        analyses = e.analyze_all([s1, s2])
        a1 = next(a for a in analyses if a.strategy_id == "s1")
        # s2's utility should be negative or zero, so no option value
        a2 = next(a for a in analyses if a.strategy_id == "s2")
        # If s2 has negative net_utility, s1 should get no option value from it
        if a2.net_utility <= 0:
            self.assertEqual(a1.option_value, 0.0)


# ── Evaluator ────────────────────────────────────────────────────


class TestStrategicEvaluator(TestCase):
    def _make_candidate(self, strategy_id: str, improvement: float,
                        risk: float = 0.10, confidence: float = 0.89):
        from core.strategy_v2.models import StrategyCandidate
        return StrategyCandidate(
            strategy_id=strategy_id,
            name=f"S {strategy_id}",
            description="Test",
            proposal_ids=["prp_001"],
            impact_by_dimension={"general": improvement},
            overall_improvement=improvement,
            risk=risk,
            implementation_cost=0.40,
            confidence=confidence,
        )

    def test_40_sorts_by_utility_descending(self):
        from core.strategy_v2.evaluator import StrategicEvaluator
        e = StrategicEvaluator()
        candidates = [
            self._make_candidate("high", 0.60),
            self._make_candidate("mid", 0.30),
            self._make_candidate("low", 0.10),
        ]
        results = e.evaluate(candidates)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0][0].strategy_id, "high")
        self.assertEqual(results[1][0].strategy_id, "mid")
        self.assertEqual(results[2][0].strategy_id, "low")

    def test_41_single_candidate(self):
        from core.strategy_v2.evaluator import StrategicEvaluator
        e = StrategicEvaluator()
        results = e.evaluate([
            self._make_candidate("only", 0.30),
        ])
        self.assertEqual(len(results), 1)

    def test_42_returns_candidate_and_analysis(self):
        from core.strategy_v2.evaluator import StrategicEvaluator
        e = StrategicEvaluator()
        results = e.evaluate([
            self._make_candidate("s1", 0.30),
        ])
        candidate, analysis = results[0]
        self.assertEqual(candidate.strategy_id, "s1")
        self.assertIsNotNone(analysis.net_utility)


# ── Selector ─────────────────────────────────────────────────────


class TestStrategicSelector(TestCase):
    def _make_candidate(self, strategy_id: str):
        from core.strategy_v2.models import StrategyCandidate
        return StrategyCandidate(
            strategy_id=strategy_id,
            name=f"S {strategy_id}",
            description="Test",
            proposal_ids=["prp_001"],
            impact_by_dimension={"general": 0.30},
            overall_improvement=0.30,
            risk=0.10,
            implementation_cost=0.40,
            confidence=0.89,
        )

    def _make_analysis(self, strategy_id: str, utility: float):
        from core.strategy_v2.models import TradeoffAnalysis
        return TradeoffAnalysis(
            strategy_id=strategy_id,
            net_utility=utility,
            dimension_scores={"improvement": utility},
            strengths=[],
            weaknesses=[],
        )

    def test_50_selects_top_candidate(self):
        from core.strategy_v2.selector import StrategicSelector
        s = StrategicSelector()
        candidates = [
            self._make_candidate("best"),
            self._make_candidate("mid"),
            self._make_candidate("worst"),
        ]
        analyses = [
            self._make_analysis("best", 0.50),
            self._make_analysis("mid", 0.30),
            self._make_analysis("worst", 0.10),
        ]
        decision = s.select(candidates, analyses)
        self.assertEqual(decision.chosen_strategy_id, "best")
        self.assertEqual(len(decision.alternative_strategy_ids), 2)

    def test_51_decision_has_rationale(self):
        from core.strategy_v2.selector import StrategicSelector
        s = StrategicSelector()
        candidates = [self._make_candidate("only")]
        analyses = [self._make_analysis("only", 0.40)]
        decision = s.select(candidates, analyses)
        self.assertIn("only", decision.rationale)
        self.assertIn("Utility", decision.rationale)
        self.assertEqual(decision.alternative_strategy_ids, [])

    def test_52_empty_candidates_raises(self):
        from core.strategy_v2.selector import StrategicSelector
        s = StrategicSelector()
        with self.assertRaises(ValueError):
            s.select([], [])

    def test_53_selected_strategy_marked(self):
        from core.strategy_v2.selector import StrategicSelector
        from core.strategy_v2.models import StrategyStatus
        s = StrategicSelector()
        candidates = [self._make_candidate("chosen")]
        analyses = [self._make_analysis("chosen", 0.40)]
        s.select(candidates, analyses)
        self.assertEqual(candidates[0].status, StrategyStatus.SELECTED)

    def test_54_decision_has_utility_scores(self):
        from core.strategy_v2.selector import StrategicSelector
        s = StrategicSelector()
        candidates = [
            self._make_candidate("a"),
            self._make_candidate("b"),
        ]
        analyses = [
            self._make_analysis("a", 0.50),
            self._make_analysis("b", 0.30),
        ]
        decision = s.select(candidates, analyses)
        self.assertIn("a", decision.utility_scores)
        self.assertIn("b", decision.utility_scores)


# ── MemoryAdapter ────────────────────────────────────────────────


class TestStrategyMemoryAdapter(TestCase):
    def setUp(self):
        from core.generalization.store import PrincipleStore
        self._tmp = tempfile.mktemp(suffix=".db")
        self.store = PrincipleStore(db_path=self._tmp)

    def tearDown(self):
        try:
            os.unlink(self._tmp)
        except Exception:
            pass

    def _make_proposal(self, proposal_id: str, status: str = "generated"):
        from core.generalization.models import ImprovementProposal, ProposalStatus
        return ImprovementProposal(
            proposal_id=proposal_id,
            target_system="browser_tool",
            proposal_type="add_capability",
            principle_id="pr_001",
            title=f"Test {proposal_id}",
            rationale="Rationale",
            expected_improvement=0.33,
            confidence=0.89,
            status=ProposalStatus(status),
        )

    def test_60_get_open_proposals_returns_generated_and_approved(self):
        from core.strategy_v2.memory_adapter import StrategyMemoryAdapter
        from core.generalization.models import ProposalStatus
        self.store.save_proposal(self._make_proposal("prp_gen", "generated"))
        self.store.save_proposal(self._make_proposal("prp_app", "approved"))
        self.store.save_proposal(self._make_proposal("prp_exp", "experimenting"))

        adapter = StrategyMemoryAdapter(self.store)
        open_proposals = adapter.get_open_proposals()
        proposal_ids = {p.proposal_id for p in open_proposals}
        self.assertIn("prp_gen", proposal_ids)
        self.assertIn("prp_app", proposal_ids)
        self.assertNotIn("prp_exp", proposal_ids)

    def test_61_get_experimenting_proposals(self):
        from core.strategy_v2.memory_adapter import StrategyMemoryAdapter
        self.store.save_proposal(self._make_proposal("prp_exp", "experimenting"))
        self.store.save_proposal(self._make_proposal("prp_gen", "generated"))

        adapter = StrategyMemoryAdapter(self.store)
        exp = adapter.get_experimenting_proposals()
        self.assertEqual(len(exp), 1)
        self.assertEqual(exp[0].proposal_id, "prp_exp")

    def test_62_count_open_proposals(self):
        from core.strategy_v2.memory_adapter import StrategyMemoryAdapter
        self.store.save_proposal(self._make_proposal("prp_1", "generated"))
        self.store.save_proposal(self._make_proposal("prp_2", "approved"))
        self.store.save_proposal(self._make_proposal("prp_3", "experimenting"))

        adapter = StrategyMemoryAdapter(self.store)
        self.assertEqual(adapter.count_open_proposals(), 2)

    def test_63_get_proposal_by_id(self):
        from core.strategy_v2.memory_adapter import StrategyMemoryAdapter
        self.store.save_proposal(self._make_proposal("prp_find"))
        adapter = StrategyMemoryAdapter(self.store)
        p = adapter.get_proposal("prp_find")
        self.assertIsNotNone(p)
        self.assertEqual(p.proposal_id, "prp_find")


# ── Full Pipeline Integration ────────────────────────────────────


class TestStrategicReasoningPipeline(TestCase):
    """End-to-end: proposals → planner → predictor → tradeoffs → evaluator → selector."""

    def setUp(self):
        from core.generalization.store import PrincipleStore
        self._tmp = tempfile.mktemp(suffix=".db")
        self.store = PrincipleStore(db_path=self._tmp)

    def tearDown(self):
        try:
            os.unlink(self._tmp)
        except Exception:
            pass

    def _make_proposal(self, proposal_id: str, target: str = "browser_tool",
                        improvement: float = 0.33, confidence: float = 0.89):
        from core.generalization.models import ImprovementProposal, ProposalStatus
        return ImprovementProposal(
            proposal_id=proposal_id,
            target_system=target,
            proposal_type="add_capability",
            principle_id="pr_001",
            title=f"Add to {target}",
            rationale=f"Improves by {improvement:.0%}",
            expected_improvement=improvement,
            confidence=confidence,
            status=ProposalStatus.APPROVED,
        )

    def test_70_end_to_end_pipeline(self):
        from core.strategy_v2.planner import StrategicPlanner
        from core.strategy_v2.predictor import OutcomePredictor
        from core.strategy_v2.tradeoffs import TradeoffEngine
        from core.strategy_v2.evaluator import StrategicEvaluator
        from core.strategy_v2.selector import StrategicSelector

        # Seed proposals
        proposals = [
            self._make_proposal("prp_a", "browser_tool", 0.33, 0.89),
            self._make_proposal("prp_b", "coding_tool", 0.25, 0.75),
            self._make_proposal("prp_c", "memory_tool", 0.40, 0.60),
        ]
        self.store.save_proposals(proposals)

        # 1. Plan
        planner = StrategicPlanner()
        candidates = planner.plan_from_proposals(proposals)
        self.assertGreater(len(candidates), 0)

        # 2. Predict
        predictor = OutcomePredictor()
        candidates = predictor.predict_all(candidates)

        # 3. Evaluate
        evaluator = StrategicEvaluator()
        results = evaluator.evaluate(candidates)
        self.assertEqual(len(results), len(candidates))

        # 4. Select
        selector = StrategicSelector()
        selected_candidates = [c for c, _ in results]
        selected_analyses = [a for _, a in results]
        decision = selector.select(selected_candidates, selected_analyses)

        self.assertIsNotNone(decision.chosen_strategy_id)
        self.assertGreater(decision.utility_scores[decision.chosen_strategy_id], 0)
        self.assertIn("utility", decision.rationale)

    def test_71_pipeline_with_multiple_same_system_proposals(self):
        """Proposals for the same system produce combined strategy."""
        from core.strategy_v2.planner import StrategicPlanner
        from core.strategy_v2.evaluator import StrategicEvaluator
        from core.strategy_v2.selector import StrategicSelector

        proposals = [
            self._make_proposal("prp_x1", "tool_x", 0.30, 0.90),
            self._make_proposal("prp_x2", "tool_x", 0.20, 0.80),
            self._make_proposal("prp_y", "tool_y", 0.35, 0.85),
        ]
        planner = StrategicPlanner()
        candidates = planner.plan_from_proposals(proposals)
        # 2 single for tool_x + 1 single for tool_y + 1 combined for tool_x = 4
        self.assertEqual(len(candidates), 4)

        evaluator = StrategicEvaluator()
        results = evaluator.evaluate(candidates)

        selector = StrategicSelector()
        selected_candidates = [c for c, _ in results]
        selected_analyses = [a for _, a in results]
        decision = selector.select(selected_candidates, selected_analyses)

        self.assertIn(decision.chosen_strategy_id,
                      {c.strategy_id for c in candidates})

    def test_72_high_improvement_low_risk_selected_over_alternatives(self):
        """The best strategy (high improvement, low risk) is selected."""
        from core.strategy_v2.planner import StrategicPlanner
        from core.strategy_v2.evaluator import StrategicEvaluator
        from core.strategy_v2.selector import StrategicSelector

        proposals = [
            self._make_proposal("prp_best", "tool_a", 0.50, 0.95),
            self._make_proposal("prp_risky", "tool_b", 0.55, 0.40),
            self._make_proposal("prp_weak", "tool_c", 0.15, 0.60),
        ]
        planner = StrategicPlanner()
        candidates = planner.plan_from_proposals(proposals)

        evaluator = StrategicEvaluator()
        results = evaluator.evaluate(candidates)

        selector = StrategicSelector()
        selected_candidates = [c for c, _ in results]
        selected_analyses = [a for _, a in results]
        decision = selector.select(selected_candidates, selected_analyses)

        # The best proposal (prp_best) should have the highest expected improvement
        chosen = next(c for c, _ in results
                      if c.strategy_id == decision.chosen_strategy_id)
        self.assertIn("50%", chosen.description or "50")

    def test_73_all_strategies_have_tradeoff_analyses(self):
        """Every strategy has a corresponding tradeoff analysis in the decision."""
        from core.strategy_v2.planner import StrategicPlanner
        from core.strategy_v2.evaluator import StrategicEvaluator
        from core.strategy_v2.selector import StrategicSelector

        proposals = [
            self._make_proposal("prp_1", "tool_a", 0.30, 0.80),
            self._make_proposal("prp_2", "tool_b", 0.35, 0.85),
        ]
        planner = StrategicPlanner()
        candidates = planner.plan_from_proposals(proposals)

        evaluator = StrategicEvaluator()
        results = evaluator.evaluate(candidates)

        selector = StrategicSelector()
        selected_candidates = [c for c, _ in results]
        selected_analyses = [a for _, a in results]
        decision = selector.select(selected_candidates, selected_analyses)

        self.assertEqual(len(decision.tradeoff_analyses), len(candidates))
        for ta in decision.tradeoff_analyses:
            self.assertIsNotNone(ta.net_utility)


# ── Executor ─────────────────────────────────────────────────────


class TestStrategyExecutor(TestCase):
    """Tests for StrategyExecutor — bridges StrategicDecision → ProposalExecutor."""

    def setUp(self):
        from core.generalization.store import PrincipleStore
        self._tmp = tempfile.mktemp(suffix=".db")
        self.store = PrincipleStore(db_path=self._tmp)
        self._make_proposals()

    def tearDown(self):
        try:
            os.unlink(self._tmp)
        except Exception:
            pass

    def _make_proposals(self):
        from core.generalization.models import ImprovementProposal, ProposalStatus
        self.proposal_a = ImprovementProposal(
            proposal_id="prp_exec_a",
            target_system="browser_tool",
            proposal_type="add_capability",
            principle_id="pr_001",
            title="Add verification to browser_tool",
            rationale="verification improves success by 33%",
            expected_improvement=0.33,
            confidence=0.89,
            status=ProposalStatus.APPROVED,
        )
        self.proposal_b = ImprovementProposal(
            proposal_id="prp_exec_b",
            target_system="browser_tool",
            proposal_type="add_capability",
            principle_id="pr_002",
            title="Add retry to browser_tool",
            rationale="retry improves success by 35%",
            expected_improvement=0.35,
            confidence=0.85,
            status=ProposalStatus.APPROVED,
        )
        self.store.save_proposals([self.proposal_a, self.proposal_b])

    def _make_candidates_and_decision(self) -> tuple:
        from core.strategy_v2.models import (
            StrategicDecision,
            StrategyCandidate,
            TradeoffAnalysis,
        )
        from core.strategy_v2.selector import StrategicSelector

        combined = StrategyCandidate(
            strategy_id="strat_combined",
            name="Combined browser_tool improvements",
            description="verification + retry for browser_tool",
            proposal_ids=["prp_exec_a", "prp_exec_b"],
            impact_by_dimension={"browser": 0.34, "general": 0.03},
            overall_improvement=0.34,
            risk=0.10,
            implementation_cost=0.50,
            confidence=0.87,
        )
        single = StrategyCandidate(
            strategy_id="strat_single",
            name="Single browser_tool improvement",
            description="verification only",
            proposal_ids=["prp_exec_a"],
            impact_by_dimension={"browser": 0.33, "general": 0.03},
            overall_improvement=0.33,
            risk=0.10,
            implementation_cost=0.40,
            confidence=0.89,
        )
        candidates = [combined, single]
        analyses = [
            TradeoffAnalysis("strat_combined", 0.42, {"improvement": 0.15}, ["improvement"], []),
            TradeoffAnalysis("strat_single", 0.38, {"improvement": 0.12}, ["low_cost"], []),
        ]
        selector = StrategicSelector()
        decision = selector.select(candidates, analyses)
        return candidates, decision

    def test_80_execute_decision_transitions_proposals_to_experimenting(self):
        from core.strategy_v2.executor import StrategyExecutor
        from core.strategy_v2.models import StrategyStatus
        from core.generalization.models import ProposalStatus

        candidates, decision = self._make_candidates_and_decision()
        executor = StrategyExecutor(self.store)
        result = executor.execute_decision(decision, candidates)

        # Both proposals should be executed
        self.assertIn("prp_exec_a", result)
        self.assertIn("prp_exec_b", result)
        self.assertIsInstance(result["prp_exec_a"], str)
        self.assertTrue(result["prp_exec_a"].startswith("exp_"))

        # Status should be EXPERIMENTING
        pa = self.store.get_proposal("prp_exec_a")
        pb = self.store.get_proposal("prp_exec_b")
        self.assertEqual(pa.status, ProposalStatus.EXPERIMENTING)
        self.assertEqual(pb.status, ProposalStatus.EXPERIMENTING)

        # Decision should be EXECUTING
        self.assertEqual(decision.status, StrategyStatus.EXECUTING)

    def test_81_execute_decision_skips_already_experimenting(self):
        from core.strategy_v2.executor import StrategyExecutor
        from core.generalization.models import ProposalStatus

        # Manually set one to EXPERIMENTING
        self.store.update_proposal_status("prp_exec_a", ProposalStatus.EXPERIMENTING)

        candidates, decision = self._make_candidates_and_decision()
        executor = StrategyExecutor(self.store)
        result = executor.execute_decision(decision, candidates)

        # Only prp_exec_b should be executed
        self.assertNotIn("prp_exec_a", result)
        self.assertIn("prp_exec_b", result)

    def test_82_execute_decision_raises_on_missing_strategy(self):
        from core.strategy_v2.executor import StrategyExecutor
        from core.strategy_v2.models import StrategicDecision

        decision = StrategicDecision(
            decision_id="dec_missing",
            chosen_strategy_id="strat_nonexistent",
            alternative_strategy_ids=[],
            rationale="",
            utility_scores={},
        )
        executor = StrategyExecutor(self.store)
        with self.assertRaises(ValueError):
            executor.execute_decision(decision, [])

    def test_83_complete_decision_promotes_proposals(self):
        from core.strategy_v2.executor import StrategyExecutor
        from core.strategy_v2.models import StrategyStatus
        from core.generalization.models import ProposalStatus

        candidates, decision = self._make_candidates_and_decision()
        executor = StrategyExecutor(self.store)
        executor.execute_decision(decision, candidates)

        # Complete with success
        result = executor.complete_decision(decision, candidates, overall_success=True)

        self.assertIn("prp_exec_a", result)
        self.assertIn("prp_exec_b", result)
        self.assertTrue(result["prp_exec_a"])
        self.assertTrue(result["prp_exec_b"])

        # Proposals should be PROMOTED
        pa = self.store.get_proposal("prp_exec_a")
        pb = self.store.get_proposal("prp_exec_b")
        self.assertEqual(pa.status, ProposalStatus.PROMOTED)
        self.assertEqual(pb.status, ProposalStatus.PROMOTED)

        # Decision should be COMPLETED
        self.assertEqual(decision.status, StrategyStatus.COMPLETED)

    def test_84_complete_decision_rejects_on_failure(self):
        from core.strategy_v2.executor import StrategyExecutor
        from core.strategy_v2.models import StrategyStatus
        from core.generalization.models import ProposalStatus

        candidates, decision = self._make_candidates_and_decision()
        executor = StrategyExecutor(self.store)
        executor.execute_decision(decision, candidates)

        # Complete with failure
        result = executor.complete_decision(decision, candidates, overall_success=False)

        self.assertFalse(result["prp_exec_a"])
        self.assertFalse(result["prp_exec_b"])

        pa = self.store.get_proposal("prp_exec_a")
        self.assertEqual(pa.status, ProposalStatus.REJECTED)

        # Decision should be SUPERSEDED
        self.assertEqual(decision.status, StrategyStatus.SUPERSEDED)

    def test_85_complete_decision_with_per_proposal_results(self):
        from core.strategy_v2.executor import StrategyExecutor
        from core.generalization.models import ProposalStatus

        candidates, decision = self._make_candidates_and_decision()
        executor = StrategyExecutor(self.store)
        executor.execute_decision(decision, candidates)

        # Mixed results: A succeeds, B fails
        per_proposal = {
            "prp_exec_a": {"success": True},
            "prp_exec_b": {"success": False},
        }
        result = executor.complete_decision(
            decision, candidates,
            overall_success=False,
            per_proposal_results=per_proposal,
        )

        self.assertTrue(result["prp_exec_a"])
        self.assertFalse(result["prp_exec_b"])

        pa = self.store.get_proposal("prp_exec_a")
        pb = self.store.get_proposal("prp_exec_b")
        self.assertEqual(pa.status, ProposalStatus.PROMOTED)
        self.assertEqual(pb.status, ProposalStatus.REJECTED)

    def test_86_complete_decision_skips_non_experimenting(self):
        from core.strategy_v2.executor import StrategyExecutor

        candidates, decision = self._make_candidates_and_decision()
        executor = StrategyExecutor(self.store)

        # Don't execute — proposals are still APPROVED, not EXPERIMENTING
        result = executor.complete_decision(decision, candidates, overall_success=True)

        # No proposals should be completed
        self.assertEqual(result, {})

    def test_87_execute_and_complete_roundtrip_persists_outcome_data_points(self):
        from core.strategy_v2.executor import StrategyExecutor

        candidates, decision = self._make_candidates_and_decision()
        executor = StrategyExecutor(self.store)
        executor.execute_decision(decision, candidates)
        executor.complete_decision(decision, candidates, overall_success=True)

        # Outcome data points should be recorded (domain=self_improvement)
        points = self.store.list_data_points(domain="self_improvement")
        self.assertGreaterEqual(len(points), 2)
        for point in points:
            self.assertTrue(point.success)
            self.assertEqual(point.domain, "self_improvement")
            self.assertIn("proposal_type", point.properties)
            self.assertIn("expected_improvement", point.properties)

    def test_88_execute_decision_with_experiment_runner_injection(self):
        """StrategyExecutor accepts a custom ProposalExecutor."""
        from core.strategy_v2.executor import StrategyExecutor
        from core.generalization.executor import ProposalExecutor

        # Inject a ProposalExecutor
        custom_executor = ProposalExecutor()
        candidates, decision = self._make_candidates_and_decision()
        executor = StrategyExecutor(self.store, proposal_executor=custom_executor)
        result = executor.execute_decision(decision, candidates)

        self.assertIn("prp_exec_a", result)
        self.assertEqual(len(result), 2)

    def test_89_complete_decision_passes_metrics_to_outcome_point(self):
        from core.strategy_v2.executor import StrategyExecutor
        from core.generalization.models import ProposalStatus

        candidates, decision = self._make_candidates_and_decision()
        executor = StrategyExecutor(self.store)
        executor.execute_decision(decision, candidates)

        per_proposal = {
            "prp_exec_a": {
                "success": True,
                "control_metrics": {"success_rate": 0.50},
                "candidate_metrics": {"success_rate": 0.85},
            },
        }
        result = executor.complete_decision(
            decision, candidates,
            overall_success=True,
            per_proposal_results=per_proposal,
        )
        self.assertTrue(result["prp_exec_a"])

        # Check data point has metrics
        points = self.store.list_data_points(
            domain="self_improvement", system_id="browser_tool",
        )
        metrics_point = None
        for p in points:
            if p.properties.get("control_success_rate") == 0.50:
                metrics_point = p
                break
        self.assertIsNotNone(metrics_point)
        self.assertEqual(metrics_point.properties["candidate_success_rate"], 0.85)


# ── Portfolio Optimizer (Phase 15.2) ─────────────────────────────


class TestResourceModels(TestCase):
    def test_90_resource_budget_defaults(self):
        from core.strategy_v2.models import ResourceBudget
        b = ResourceBudget()
        self.assertEqual(b.effort_budget, 40.0)
        self.assertEqual(b.max_concurrent, 1)
        self.assertEqual(b.min_utility_threshold, 0.0)

    def test_91_resource_budget_custom(self):
        from core.strategy_v2.models import ResourceBudget
        b = ResourceBudget(effort_budget=100.0, max_concurrent=3,
                            min_utility_threshold=0.1)
        self.assertEqual(b.effort_budget, 100.0)
        self.assertEqual(b.max_concurrent, 3)
        self.assertEqual(b.min_utility_threshold, 0.1)

    def test_92_portfolio_allocation_empty(self):
        from core.strategy_v2.models import PortfolioAllocation
        from core.strategy_v2.models import ResourceBudget
        budget = ResourceBudget()
        a = PortfolioAllocation(
            selected=[], selected_analyses=[],
            deferred=[], deferred_analyses=[],
            total_effort_consumed=0.0,
            total_expected_value=0.0,
            remaining_effort=budget.effort_budget,
            rationale="Nothing to allocate.",
        )
        self.assertEqual(len(a.selected), 0)
        self.assertEqual(a.remaining_effort, 40.0)

    def test_93_portfolio_allocation_to_dict(self):
        from core.strategy_v2.models import PortfolioAllocation
        from core.strategy_v2.models import StrategyCandidate, TradeoffAnalysis
        c = StrategyCandidate(
            strategy_id="s1", name="T1", description="",
            proposal_ids=[], impact_by_dimension={},
            overall_improvement=0.3, risk=0.1,
            implementation_cost=0.4, confidence=0.89,
        )
        a = TradeoffAnalysis(strategy_id="s1", net_utility=0.42,
                              dimension_scores={}, strengths=[], weaknesses=[])
        alloc = PortfolioAllocation(
            selected=[c], selected_analyses=[a],
            deferred=[], deferred_analyses=[],
            total_effort_consumed=10.0,
            total_expected_value=0.42,
            remaining_effort=30.0,
        )
        d = alloc.to_dict()
        self.assertEqual(len(d["selected"]), 1)
        self.assertEqual(d["total_effort_consumed"], 10.0)


class TestPortfolioOptimizer(TestCase):
    def _make_candidate(self, strategy_id: str, name: str,
                        improvement: float = 0.30, risk: float = 0.10,
                        cost: float = 0.40, confidence: float = 0.89):
        from core.strategy_v2.models import StrategyCandidate
        return StrategyCandidate(
            strategy_id=strategy_id, name=name, description="",
            proposal_ids=["prp_" + strategy_id],
            impact_by_dimension={"general": improvement},
            overall_improvement=improvement, risk=risk,
            implementation_cost=cost, confidence=confidence,
        )

    def _make_analysis(self, strategy_id: str, utility: float):
        from core.strategy_v2.models import TradeoffAnalysis
        return TradeoffAnalysis(
            strategy_id=strategy_id, net_utility=utility,
            dimension_scores={"improvement": utility},
            strengths=[], weaknesses=[],
        )

    def test_100_selects_best_strategies_within_budget(self):
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        candidates = [
            self._make_candidate("s1", "High value, low cost",
                                 improvement=0.50, cost=0.20),
            self._make_candidate("s2", "Medium value, high cost",
                                 improvement=0.40, cost=0.80),
            self._make_candidate("s3", "Low value, low cost",
                                 improvement=0.15, cost=0.10),
        ]
        analyses = [
            self._make_analysis("s1", 0.45),
            self._make_analysis("s2", 0.25),
            self._make_analysis("s3", 0.10),
        ]
        budget = ResourceBudget(effort_budget=40.0)
        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize(candidates, analyses, budget)

        # s1 (effort=8) and s3 (effort=4) should fit; s2 (effort=32) alone
        # but s1 has best value/cost, so both fit
        selected_ids = {c.strategy_id for c in allocation.selected}
        self.assertIn("s1", selected_ids)
        self.assertIn("s3", selected_ids)

    def test_101_highest_value_cost_ratio_selected_first(self):
        """Strategies are selected by value/cost ratio, not raw utility."""
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        candidates = [
            self._make_candidate("high_ratio", "Efficient", improvement=0.30,
                                 cost=0.10),  # value/cost = 2.0
            self._make_candidate("low_ratio", "Inefficient", improvement=0.50,
                                 cost=0.90),  # value/cost = 0.56
        ]
        analyses = [
            self._make_analysis("high_ratio", 0.20),
            self._make_analysis("low_ratio", 0.35),
        ]
        budget = ResourceBudget(effort_budget=15.0)
        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize(candidates, analyses, budget)

        # high_ratio has better value/cost even though lower raw utility
        selected_ids = {c.strategy_id for c in allocation.selected}
        self.assertIn("high_ratio", selected_ids)

    def test_102_negative_utility_excluded(self):
        """Strategies with utility below min_utility_threshold are excluded."""
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        candidates = [
            self._make_candidate("good", "Good", improvement=0.30, cost=0.20),
            self._make_candidate("bad", "Bad", improvement=0.05, cost=0.10),
        ]
        analyses = [
            self._make_analysis("good", 0.20),
            self._make_analysis("bad", 0.0),  # exactly at threshold (default 0.0)
        ]
        budget = ResourceBudget(effort_budget=40.0)
        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize(candidates, analyses, budget)

        selected_ids = {c.strategy_id for c in allocation.selected}
        self.assertIn("good", selected_ids)
        # bad has utility=0.0 which meets threshold, so it should be allowed
        # Now test with a positive threshold
        budget2 = ResourceBudget(effort_budget=40.0, min_utility_threshold=0.05)
        allocation2 = optimizer.optimize(candidates, analyses, budget2)
        selected2_ids = {c.strategy_id for c in allocation2.selected}
        self.assertIn("good", selected2_ids)
        # bad (utility=0.0) should be excluded
        self.assertNotIn("bad", selected2_ids)

    def test_103_deferred_when_budget_exhausted(self):
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        candidates = [
            self._make_candidate("a", "A", improvement=0.30, cost=0.50),
            self._make_candidate("b", "B", improvement=0.25, cost=0.50),
            self._make_candidate("c", "C", improvement=0.20, cost=0.50),
        ]
        analyses = [
            self._make_analysis("a", 0.25),
            self._make_analysis("b", 0.20),
            self._make_analysis("c", 0.15),
        ]
        # Budget = 40 units → each costs 20 → only 2 fit
        budget = ResourceBudget(effort_budget=40.0)
        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize(candidates, analyses, budget)

        self.assertEqual(len(allocation.selected), 2)
        self.assertEqual(len(allocation.deferred), 1)

        # The two best-value should be selected (a and b)
        selected_ids = {c.strategy_id for c in allocation.selected}
        self.assertIn("a", selected_ids)
        self.assertIn("b", selected_ids)
        self.assertNotIn("c", selected_ids)

        deferred_ids = {c.strategy_id for c in allocation.deferred}
        self.assertIn("c", deferred_ids)

    def test_104_all_fit_when_enough_budget(self):
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        candidates = [
            self._make_candidate("a", "A", improvement=0.30, cost=0.20),
            self._make_candidate("b", "B", improvement=0.25, cost=0.20),
        ]
        analyses = [
            self._make_analysis("a", 0.25),
            self._make_analysis("b", 0.20),
        ]
        budget = ResourceBudget(effort_budget=40.0)
        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize(candidates, analyses, budget)

        self.assertEqual(len(allocation.selected), 2)
        self.assertEqual(len(allocation.deferred), 0)

    def test_105_zero_cost_strategies_always_included(self):
        """Zero-cost strategies are always selected regardless of utility."""
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        candidates = [
            self._make_candidate("free", "Free", improvement=0.10, cost=0.0),
            self._make_candidate("costly", "Costly", improvement=0.50, cost=0.90),
        ]
        analyses = [
            self._make_analysis("free", 0.05),
            self._make_analysis("costly", 0.35),
        ]
        # Tight budget: only 10 units
        budget = ResourceBudget(effort_budget=10.0)
        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize(candidates, analyses, budget)

        selected_ids = {c.strategy_id for c in allocation.selected}
        self.assertIn("free", selected_ids)
        # costly costs 9 units and has high ratio, should also fit
        self.assertIn("costly", selected_ids)

    def test_106_select_best_returns_top_fitting_strategy(self):
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        candidates = [
            self._make_candidate("s1", "Best", improvement=0.30, cost=0.20),
            self._make_candidate("s2", "Cheaper", improvement=0.10, cost=0.05),
        ]
        analyses = [
            self._make_analysis("s1", 0.25),
            self._make_analysis("s2", 0.08),
        ]
        budget = ResourceBudget(effort_budget=40.0)
        optimizer = PortfolioOptimizer()
        result = optimizer.select_best(candidates, analyses, budget)
        self.assertIsNotNone(result)
        best_candidate, best_analysis = result
        # s2 has higher value/cost ratio (0.08/0.05=1.60 vs 0.25/0.20=1.25)
        self.assertEqual(best_candidate.strategy_id, "s2")

    def test_107_select_best_returns_none_when_nothing_fits(self):
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        candidates = [
            self._make_candidate("s1", "Too expensive", improvement=0.30, cost=10.0),
        ]
        analyses = [
            self._make_analysis("s1", 0.25),
        ]
        budget = ResourceBudget(effort_budget=5.0)
        optimizer = PortfolioOptimizer()
        result = optimizer.select_best(candidates, analyses, budget)
        self.assertIsNone(result)

    def test_108_empty_candidates(self):
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize([], [], ResourceBudget())
        self.assertEqual(len(allocation.selected), 0)
        self.assertEqual(len(allocation.deferred), 0)
        self.assertEqual(allocation.remaining_effort, 40.0)

    def test_109_rationale_includes_value_cost_ratio(self):
        """The rationale string includes value/cost ratio for transparency."""
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        candidates = [
            self._make_candidate("s1", "Test strategy",
                                 improvement=0.30, cost=0.20),
        ]
        analyses = [
            self._make_analysis("s1", 0.25),
        ]
        budget = ResourceBudget(effort_budget=40.0)
        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize(candidates, analyses, budget)

        self.assertIn("value/cost", allocation.rationale)
        self.assertIn("Test strategy", allocation.rationale)

    def test_110_effort_computation_correct(self):
        """Total effort consumed equals sum of implementation_cost * budget."""
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget

        candidates = [
            self._make_candidate("a", "A", improvement=0.30, cost=0.25),
            self._make_candidate("b", "B", improvement=0.20, cost=0.35),
        ]
        analyses = [
            self._make_analysis("a", 0.20),
            self._make_analysis("b", 0.15),
        ]
        budget = ResourceBudget(effort_budget=100.0)
        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize(candidates, analyses, budget)

        # 0.25 * 100 + 0.35 * 100 = 60
        self.assertAlmostEqual(allocation.total_effort_consumed, 60.0)
        self.assertAlmostEqual(allocation.remaining_effort, 40.0)

    def test_111_portfolio_wired_to_pipeline(self):
        """End-to-end: proposals → planner → tradeoffs → portfolio optimizer."""
        from core.strategy_v2.planner import StrategicPlanner
        from core.strategy_v2.tradeoffs import TradeoffEngine
        from core.strategy_v2.portfolio import PortfolioOptimizer
        from core.strategy_v2.models import ResourceBudget
        from core.generalization.models import ImprovementProposal, ProposalStatus

        proposals = [
            ImprovementProposal(
                proposal_id="prp_pa", target_system="browser_tool",
                proposal_type="add_capability", principle_id="pr_001",
                title="Verification", rationale="33% improvement",
                expected_improvement=0.33, confidence=0.89,
                status=ProposalStatus.APPROVED,
            ),
            ImprovementProposal(
                proposal_id="prp_pb", target_system="coding_tool",
                proposal_type="modify_behavior", principle_id="pr_002",
                title="Retry", rationale="35% improvement",
                expected_improvement=0.35, confidence=0.75,
                status=ProposalStatus.APPROVED,
            ),
            ImprovementProposal(
                proposal_id="prp_pc", target_system="research_tool",
                proposal_type="add_capability", principle_id="pr_003",
                title="Memory", rationale="25% improvement",
                expected_improvement=0.25, confidence=0.60,
                status=ProposalStatus.APPROVED,
            ),
        ]

        planner = StrategicPlanner()
        candidates = planner.plan_from_proposals(proposals)

        tradeoffs = TradeoffEngine()
        analyses = tradeoffs.analyze_all(candidates)

        # Tight budget: only best strategies fit
        budget = ResourceBudget(effort_budget=50.0)
        optimizer = PortfolioOptimizer()
        allocation = optimizer.optimize(candidates, analyses, budget)

        self.assertGreater(len(allocation.selected), 0)
        self.assertLessEqual(
            allocation.total_effort_consumed,
            budget.effort_budget,
        )
        for c in allocation.selected:
            self.assertIn(c, candidates)
        for c in allocation.deferred:
            self.assertIn(c, candidates)
