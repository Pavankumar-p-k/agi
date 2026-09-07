"""Tests for Phase 12 — Strategic Reasoning Layer.

Covers strategy generation, prediction, evaluation, selection,
and the full pipeline.
"""

from datetime import datetime
from unittest import TestCase

from core.strategy.calibration import (
    CalibrationMetrics,
    CalibrationRecord,
    CalibrationStore,
    PredictionCalibrator,
)
from core.strategy.generator import StrategyGenerator, classify_goal
from core.strategy.models import Prediction, Strategy, StrategyDecision, StrategyTag
from core.strategy.predictor import OutcomePredictor
from core.strategy.evaluator import StrategyEvaluator
from core.strategy.selector import StrategySelector
from core.strategy.memory_adapter import MemoryAdapter, PastActivity, DomainEvidence
from core.strategy.models import EvidenceBundle


def _make_strategy(name: str = "MVP-first",
                   goal: str = "Build a coffee shop app",
                   tags: list[StrategyTag] | None = None) -> Strategy:
    return Strategy(
        name=name,
        description=f"{name} strategy",
        goal=goal,
        tags=tags or [StrategyTag.MVP],
        prediction=None,
    )


def _make_prediction(sp: float = 0.8, dur: float = 10, risk: float = 0.2,
                     conf: float = 0.6, evidence: int = 5) -> Prediction:
    return Prediction(
        success_probability=sp,
        estimated_duration_days=dur,
        estimated_risk=risk,
        estimated_effort=dur * 0.5,
        confidence=conf,
        evidence_count=evidence,
    )


# ─── models.py ─────────────────────────────────────────────────────────────


class TestStrategyModels(TestCase):
    """Strategy, Prediction, StrategyDecision model behavior."""

    def test_01_strategy_creation(self):
        s = _make_strategy()
        self.assertEqual(s.name, "MVP-first")
        self.assertEqual(s.goal, "Build a coffee shop app")
        self.assertIn(StrategyTag.MVP, s.tags)
        self.assertIsNone(s.prediction)

    def test_02_strategy_to_dict(self):
        s = _make_strategy()
        d = s.to_dict(include_prediction=False)
        self.assertIn("name", d)
        self.assertIn("goal", d)
        self.assertNotIn("prediction", d)

    def test_03_strategy_to_dict_with_prediction(self):
        s = _make_strategy()
        s.prediction = _make_prediction()
        d = s.to_dict()
        self.assertIn("prediction", d)
        self.assertIn("success_probability", d["prediction"])

    def test_04_prediction_creation(self):
        p = _make_prediction()
        self.assertAlmostEqual(p.success_probability, 0.8)
        self.assertAlmostEqual(p.estimated_duration_days, 10.0)
        self.assertAlmostEqual(p.estimated_risk, 0.2)
        self.assertAlmostEqual(p.confidence, 0.6)
        self.assertEqual(p.evidence_count, 5)

    def test_05_prediction_to_dict(self):
        p = _make_prediction()
        d = p.to_dict()
        self.assertIn("success_probability", d)
        self.assertIn("estimated_duration_days", d)

    def test_06_strategy_decision_creation(self):
        s = _make_strategy()
        s.prediction = _make_prediction()
        d = StrategyDecision(
            decision_id="sd_test_001",
            goal="Build a coffee shop app",
            timestamp=datetime.utcnow(),
            strategies_considered=[s],
            chosen_strategy=s,
            confidence=0.85,
        )
        self.assertEqual(d.decision_id, "sd_test_001")
        self.assertEqual(len(d.strategies_considered), 1)
        self.assertIsNone(d.actual_success)

    def test_07_strategy_decision_prediction_error(self):
        s = _make_strategy()
        s.prediction = _make_prediction(dur=10)
        d = StrategyDecision(
            decision_id="sd_test_002",
            goal="Test",
            timestamp=datetime.utcnow(),
            strategies_considered=[s],
            chosen_strategy=s,
            confidence=0.8,
            actual_success=True,
            actual_duration_days=13,
        )
        error = d.prediction_error_duration
        self.assertIsNotNone(error)
        self.assertAlmostEqual(error, 0.3)  # (13-10)/10 = 0.3

    def test_08_strategy_decision_no_prediction_no_error(self):
        s = _make_strategy()
        d = StrategyDecision(
            decision_id="sd_test_003",
            goal="Test",
            timestamp=datetime.utcnow(),
            strategies_considered=[s],
            chosen_strategy=s,
            confidence=0.5,
            actual_duration_days=10,
        )
        self.assertIsNone(d.prediction_error_duration)


# ─── generator.py ──────────────────────────────────────────────────────────


class TestStrategyGenerator(TestCase):
    """StrategyGenerator — goal classification and candidate generation."""

    def setUp(self):
        self._gen = StrategyGenerator()

    def test_10_classify_build(self):
        self.assertEqual(classify_goal("Build a coffee shop app"), "build")
        self.assertEqual(classify_goal("Create a payment system"), "build")
        self.assertEqual(classify_goal("Develop a mobile app"), "build")

    def test_11_classify_research(self):
        self.assertEqual(classify_goal("Research competitor apps"), "research")
        self.assertEqual(classify_goal("Investigate market trends"), "research")
        self.assertEqual(classify_goal("Study user behavior"), "research")

    def test_12_classify_refactor(self):
        self.assertEqual(classify_goal("Refactor the payment module"), "refactor")
        self.assertEqual(classify_goal("Rewrite auth system"), "refactor")

    def test_13_classify_explore(self):
        self.assertEqual(classify_goal("Explore API options"), "explore")
        self.assertEqual(classify_goal("Find available libraries"), "explore")

    def test_14_classify_default(self):
        self.assertEqual(classify_goal("Coffee shop app"), "build")

    def test_15_generate_build_strategies(self):
        strategies = self._gen.generate("Build a coffee shop app")
        names = [s.name for s in strategies]
        self.assertIn("MVP-first", names)
        self.assertIn("Feature-complete", names)
        self.assertIn("Quality-first", names)
        self.assertIn("Research-driven", names)
        self.assertEqual(len(strategies), 4)

    def test_16_generate_research_strategies(self):
        strategies = self._gen.generate("Research LLM benchmarks", goal_type="research")
        names = [s.name for s in strategies]
        self.assertIn("Broad-survey", names)
        self.assertIn("Deep-dive", names)
        self.assertIn("Targeted", names)
        self.assertEqual(len(strategies), 3)

    def test_17_generate_refactor_strategies(self):
        strategies = self._gen.generate("Refactor auth module", goal_type="refactor")
        names = [s.name for s in strategies]
        self.assertIn("Minimal-change", names)
        self.assertIn("Incremental", names)
        self.assertIn("Full-refactor", names)

    def test_18_generate_preserves_goal(self):
        strategies = self._gen.generate("Build analytics dashboard")
        for s in strategies:
            self.assertEqual(s.goal, "Build analytics dashboard")

    def test_19_generate_assigns_tags(self):
        strategies = self._gen.generate("Build app")
        for s in strategies:
            self.assertGreater(len(s.tags), 0)


# ─── predictor.py ──────────────────────────────────────────────────────────


class TestOutcomePredictor(TestCase):
    """OutcomePredictor — deterministic prediction based on strategy tags."""

    def setUp(self):
        self._pred = OutcomePredictor()

    def test_20_predict_mvp_fast_and_safe(self):
        s = _make_strategy("MVP-first", tags=[StrategyTag.MVP])
        p = self._pred.predict(s, goal_type="build")
        self.assertGreater(p.success_probability, 0.75)
        self.assertLess(p.estimated_duration_days, 12)
        self.assertLess(p.estimated_risk, 0.3)

    def test_21_predict_feature_complete_slower_riskier(self):
        s = _make_strategy("Feature-complete", tags=[StrategyTag.FEATURE_COMPLETE])
        p = self._pred.predict(s, goal_type="build")
        self.assertGreater(p.estimated_duration_days, 12)
        self.assertGreaterEqual(p.estimated_risk, 0.3)

    def test_22_predict_quality_first_high_success(self):
        s = _make_strategy("Quality-first", tags=[StrategyTag.QUALITY_FIRST])
        p = self._pred.predict(s, goal_type="build")
        self.assertGreater(p.success_probability, 0.78)

    def test_23_predict_research_targeted(self):
        s = _make_strategy("Targeted", tags=[StrategyTag.SAFE])
        p = self._pred.predict(s, goal_type="research")
        self.assertGreater(p.success_probability, 0.8)
        self.assertLess(p.estimated_duration_days, 5)

    def test_24_predict_returns_all_fields(self):
        s = _make_strategy("MVP-first", tags=[StrategyTag.MVP])
        p = self._pred.predict(s, goal_type="build")
        self.assertIsNotNone(p.success_probability)
        self.assertIsNotNone(p.estimated_duration_days)
        self.assertIsNotNone(p.estimated_risk)
        self.assertIsNotNone(p.estimated_effort)
        self.assertIsNotNone(p.confidence)

    def test_25_predict_all_enriches_in_place(self):
        strategies = [
            _make_strategy("A", tags=[StrategyTag.MVP]),
            _make_strategy("B", tags=[StrategyTag.FEATURE_COMPLETE]),
        ]
        result = self._pred.predict_all(strategies, goal_type="build")
        for s in result:
            self.assertIsNotNone(s.prediction)

    def test_26_predictions_differ_by_tag(self):
        mvp = _make_strategy("MVP", tags=[StrategyTag.MVP])
        fc = _make_strategy("Full", tags=[StrategyTag.FEATURE_COMPLETE])
        p_mvp = self._pred.predict(mvp, "build")
        p_fc = self._pred.predict(fc, "build")
        self.assertNotEqual(p_mvp.estimated_duration_days,
                            p_fc.estimated_duration_days)


# ─── evaluator.py ──────────────────────────────────────────────────────────


class TestStrategyEvaluator(TestCase):
    """StrategyEvaluator — scoring and ranking."""

    def setUp(self):
        self._eval = StrategyEvaluator()

    def test_30_score_high_success_low_risk_is_best(self):
        good = _make_prediction(sp=0.9, dur=5, risk=0.1)
        bad = _make_prediction(sp=0.4, dur=30, risk=0.7)
        self.assertGreater(self._eval.score(good), self._eval.score(bad))

    def test_31_score_bounds(self):
        p = _make_prediction(sp=0.5, dur=14, risk=0.3, conf=0.5)
        score = self._eval.score(p)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_32_score_perfect_prediction(self):
        p = _make_prediction(sp=1.0, dur=1, risk=0.0, conf=1.0)
        score = self._eval.score(p)
        self.assertAlmostEqual(score, 1.0, places=2)

    def test_33_score_none_returns_zero(self):
        self.assertAlmostEqual(self._eval.score(None), 0.0)

    def test_34_ordered_returns_sorted(self):
        strategies = [
            _make_strategy("A", tags=[StrategyTag.MVP]),
            _make_strategy("B", tags=[StrategyTag.FEATURE_COMPLETE]),
        ]
        pred = OutcomePredictor()
        pred.predict_all(strategies, "build")
        ordered = self._eval.ordered(strategies)
        self.assertEqual(len(ordered), 2)
        # Higher score should come first
        self.assertGreaterEqual(ordered[0][1], ordered[1][1])

    def test_35_ordered_skips_no_prediction(self):
        strategies = [
            _make_strategy("A"),
            _make_strategy("B"),
        ]
        strategies[1].prediction = _make_prediction()
        ordered = self._eval.ordered(strategies)
        self.assertEqual(len(ordered), 1)


# ─── selector.py ───────────────────────────────────────────────────────────


class TestStrategySelector(TestCase):
    """StrategySelector — picks best strategy with reasoning."""

    def setUp(self):
        self._pred = OutcomePredictor()
        self._sel = StrategySelector()

    def test_40_select_returns_chosen_and_decision(self):
        strategies = self._make_scored(["Build app"])
        chosen, decision = self._sel.select(strategies)
        self.assertIsNotNone(chosen)
        self.assertIsNotNone(decision)
        self.assertIn(chosen.name, [s.name for s in strategies])

    def test_41_select_empty_returns_none(self):
        chosen, decision = self._sel.select([])
        self.assertIsNone(chosen)
        self.assertIsNone(decision)

    def test_42_select_choses_highest_score(self):
        strategies = self._make_scored(["Build app"])
        chosen, _ = self._sel.select(strategies)
        # MVP-first should score highest (fast, safe, high success)
        self.assertEqual(chosen.name, "MVP-first")

    def test_43_select_with_reasoning_includes_trace(self):
        strategies = self._make_scored(["Build app"])
        result = self._sel.select_with_reasoning(strategies)
        self.assertIn("chosen", result)
        self.assertIn("reasoning", result)
        self.assertIn("ranking", result)
        self.assertIn("confidence", result)

    def test_44_decision_contains_strategies(self):
        strategies = self._make_scored(["Build app"])
        _, decision = self._sel.select(strategies)
        self.assertEqual(len(decision.strategies_considered), 4)
        self.assertEqual(decision.goal, "Build app")

    def _make_scored(self, goals: list[str]) -> list[Strategy]:
        strategies = self._gen_strategies(goals)
        return self._pred.predict_all(strategies)

    @staticmethod
    def _gen_strategies(goals: list[str]) -> list[Strategy]:
        gen = StrategyGenerator()
        result: list[Strategy] = []
        for g in goals:
            result.extend(gen.generate(g))
        return result


# ─── memory_adapter.py ─────────────────────────────────────────────────────


class TestMemoryAdapter(TestCase):
    """MemoryAdapter — evidence query layer (stubs until Phase 12.4+)."""

    def setUp(self):
        self._adapter = MemoryAdapter()

    def test_50_query_similar_activities_returns_empty(self):
        results = self._adapter.query_similar_activities("Build app")
        self.assertEqual(results, [])

    def test_51_query_domain_evidence_returns_empty(self):
        results = self._adapter.query_domain_evidence(["android", "web"])
        self.assertEqual(results, [])

    def test_52_query_research_facts_returns_empty(self):
        results = self._adapter.query_research_facts("Build app")
        self.assertEqual(results, [])

    def test_53_query_experiment_results_returns_empty(self):
        results = self._adapter.query_experiment_results(["mvp"])
        self.assertEqual(results, [])


# ─── full pipeline integration ─────────────────────────────────────────────


class TestStrategyPipeline(TestCase):
    """End-to-end: Goal → Generator → Predictor → Evaluator → Selector."""

    def test_60_full_pipeline_build_goal(self):
        goal = "Build a coffee shop app"

        gen = StrategyGenerator()
        pred = OutcomePredictor()
        eval = StrategyEvaluator()
        sel = StrategySelector()

        strategies = gen.generate(goal)
        self.assertGreater(len(strategies), 1)

        pred.predict_all(strategies)
        for s in strategies:
            self.assertIsNotNone(s.prediction)

        ordered = eval.ordered(strategies)
        self.assertEqual(len(ordered), len(strategies))
        self.assertGreaterEqual(ordered[0][1], ordered[-1][1])

        chosen, decision = sel.select(strategies)
        self.assertIsNotNone(chosen)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.goal, goal)
        self.assertGreater(decision.confidence, 0.0)

    def test_61_full_pipeline_research_goal(self):
        goal = "Research payment API options"

        gen = StrategyGenerator()
        pred = OutcomePredictor()
        eval = StrategyEvaluator()
        sel = StrategySelector()

        strategies = gen.generate(goal)
        pred.predict_all(strategies)
        chosen, decision = sel.select(strategies)

        self.assertIsNotNone(chosen)
        self.assertEqual(len(decision.strategies_considered), 3)

    def test_62_pipeline_different_goals_different_strategies(self):
        build = StrategyGenerator().generate("Build an Android app")
        research = StrategyGenerator().generate("Research competitor pricing",
                                                 goal_type="research")

        build_names = {s.name for s in build}
        research_names = {s.name for s in research}

        self.assertNotEqual(build_names, research_names)
        self.assertIn("MVP-first", build_names)
        self.assertIn("Broad-survey", research_names)


# ─── calibration.py — Phase 12.4 ─────────────────────────────────────────


def _make_decision(decision_id: str = "sd_cal_001",
                   goal: str = "Build a coffee shop app",
                   chosen_name: str = "MVP-first",
                   prediction: Prediction | None = None,
                   actual_success: bool | None = None,
                   actual_duration: float | None = None) -> StrategyDecision:
    s = Strategy(
        name=chosen_name,
        description=f"{chosen_name} strategy",
        goal=goal,
        tags=[StrategyTag.MVP, StrategyTag.SAFE],
        prediction=prediction,
    )
    return StrategyDecision(
        decision_id=decision_id,
        goal=goal,
        timestamp=datetime.utcnow(),
        strategies_considered=[s],
        chosen_strategy=s,
        confidence=0.8,
        actual_success=actual_success,
        actual_duration_days=actual_duration,
    )


class TestCalibrationModels(TestCase):
    """CalibrationRecord and CalibrationMetrics data behavior."""

    def test_70_calibration_record_creation(self):
        r = CalibrationRecord(
            decision_id="sd_001",
            goal="Build app",
            goal_type="build",
            strategy_name="MVP-first",
            tags=["mvp", "safe"],
            predicted_success=0.8,
            predicted_duration_days=10.0,
            predicted_risk=0.2,
            actual_success=True,
            actual_duration_days=13.0,
            duration_error=0.3,
            success_correct=True,
        )
        self.assertEqual(r.decision_id, "sd_001")
        self.assertAlmostEqual(r.duration_error, 0.3)

    def test_71_calibration_record_to_dict(self):
        r = CalibrationRecord(
            decision_id="sd_002", goal="Test", goal_type="build",
            strategy_name="MVP", tags=["mvp"],
            predicted_success=0.8, predicted_duration_days=10.0,
            predicted_risk=0.2, actual_success=True,
            actual_duration_days=12.0, duration_error=0.2, success_correct=True,
        )
        d = r.to_dict()
        self.assertIn("decision_id", d)
        self.assertIn("duration_error", d)

    def test_72_calibration_metrics_defaults(self):
        m = CalibrationMetrics()
        self.assertEqual(m.record_count, 0)
        self.assertEqual(m.duration_bias, 0.0)
        self.assertIsNone(m.duration_std)


class TestCalibrationStore(TestCase):
    """CalibrationStore — storing records and computing metrics."""

    def setUp(self):
        self._store = CalibrationStore()

    def _record(self, decision_id: str, goal_type: str = "build",
                duration_error: float = 0.0, success: bool = True,
                tags: list[str] | None = None) -> CalibrationRecord:
        p = _make_prediction(dur=10, sp=0.8)
        d = _make_decision(decision_id=decision_id, prediction=p,
                           actual_success=success, actual_duration=10 * (1 + duration_error))
        return self._store.record(d, goal_type, success, 10 * (1 + duration_error))

    def test_73_record_creates_entry(self):
        self._record("sd_001")
        self.assertEqual(self._store.record_count(), 1)

    def test_74_record_without_prediction(self):
        d = _make_decision("sd_nopred", prediction=None,
                           actual_success=True, actual_duration=15.0)
        r = self._store.record(d, "build", True, 15.0)
        self.assertEqual(r.duration_error, 0.0)

    def test_75_get_metrics_empty(self):
        m = self._store.get_metrics()
        self.assertEqual(m.record_count, 0)

    def test_76_get_metrics_single_record(self):
        self._record("sd_001", duration_error=0.3)
        m = self._store.get_metrics(goal_type="build")
        self.assertEqual(m.record_count, 1)
        self.assertAlmostEqual(m.duration_bias, 0.3)

    def test_77_get_metrics_filter_by_goal_type(self):
        self._record("sd_001", goal_type="build", duration_error=0.2)
        self._record("sd_002", goal_type="research", duration_error=-0.1)
        m = self._store.get_metrics(goal_type="build")
        self.assertEqual(m.record_count, 1)
        self.assertAlmostEqual(m.duration_bias, 0.2)

    def test_78_get_metrics_filter_by_tags(self):
        p = _make_prediction(dur=10, sp=0.8)
        d1 = _make_decision("sd_001", chosen_name="MVP-first", prediction=p)
        self._store.record(d1, "build", True, 12.0)

        s2 = Strategy(name="Deep-dive", description="Research", goal="Test",
                       tags=[StrategyTag.FEATURE_COMPLETE], prediction=p)
        d2 = StrategyDecision(
            decision_id="sd_002", goal="Test", timestamp=datetime.utcnow(),
            strategies_considered=[s2], chosen_strategy=s2, confidence=0.8,
            actual_success=True, actual_duration_days=15.0,
        )
        self._store.record(d2, "build", True, 15.0)

        m = self._store.get_metrics(tags=["mvp"])
        self.assertEqual(m.record_count, 1)

    def test_79_get_metrics_computes_bias(self):
        self._record("sd_001", duration_error=0.2)
        self._record("sd_002", duration_error=0.4)
        self._record("sd_003", duration_error=0.0)
        m = self._store.get_metrics()
        self.assertEqual(m.record_count, 3)
        self.assertAlmostEqual(m.duration_bias, 0.2)

    def test_80_get_metrics_computes_accuracy(self):
        p = _make_prediction(sp=0.8)
        d1 = _make_decision("sd_001", prediction=p, actual_success=True)
        self._store.record(d1, "build", True, 10.0)

        d2 = _make_decision("sd_002", prediction=p, actual_success=True)
        self._store.record(d2, "build", True, 10.0)

        d3 = _make_decision("sd_003", prediction=p, actual_success=False)
        self._store.record(d3, "build", False, 15.0)

        d4 = _make_decision("sd_004", prediction=p, actual_success=False)
        self._store.record(d4, "build", False, 15.0)

        m = self._store.get_metrics()
        self.assertEqual(m.record_count, 4)
        # sp=0.8 predicts success → 2 correct (sd_001, sd_002), 2 wrong (sd_003, sd_004)
        self.assertAlmostEqual(m.calibration_accuracy, 0.5)

    def test_81_get_metrics_std_with_two_records(self):
        self._record("sd_001", duration_error=0.2)
        self._record("sd_002", duration_error=0.4)
        m = self._store.get_metrics()
        self.assertIsNotNone(m.duration_std)

    def test_82_clear_removes_all(self):
        self._record("sd_001")
        self._record("sd_002")
        self.assertEqual(self._store.record_count(), 2)
        self._store.clear()
        self.assertEqual(self._store.record_count(), 0)


class TestPredictionCalibrator(TestCase):
    """PredictionCalibrator — adjusts predictions based on calibration data."""

    def setUp(self):
        self._store = CalibrationStore()
        self._cal = PredictionCalibrator(store=self._store)

    def _seed(self, count: int = 3, duration_error: float = 0.3,
              success: bool = True, goal_type: str = "build",
              tags: list[str] | None = None):
        tags = tags or ["mvp", "safe"]
        for i in range(count):
            p = _make_prediction(dur=10, sp=0.8)
            s = Strategy(name=f"Strategy-{i}", description="Test",
                         goal="Build app", tags=[StrategyTag(t) for t in tags],
                         prediction=p)
            d = StrategyDecision(
                decision_id=f"sd_seed_{i}", goal="Build app",
                timestamp=datetime.utcnow(),
                strategies_considered=[s], chosen_strategy=s, confidence=0.8,
                actual_success=success,
                actual_duration_days=10 * (1 + duration_error),
            )
            self._store.record(d, goal_type, success, 10 * (1 + duration_error))

    def test_85_no_calibration_without_evidence(self):
        p = _make_prediction(dur=10, sp=0.8)
        result = self._cal.calibrate(p, "build", ["mvp"])
        self.assertEqual(result.estimated_duration_days, p.estimated_duration_days)
        self.assertEqual(result.success_probability, p.success_probability)

    def test_86_calibrate_duration_with_bias(self):
        self._seed(count=3, duration_error=0.3)
        p = _make_prediction(dur=10, sp=0.8)
        result = self._cal.calibrate(p, "build", ["mvp", "safe"])
        # bias 0.3 → correction factor 1.0 + (0.3 * 0.5) = 1.15
        expected = 10 * 1.15
        self.assertAlmostEqual(result.estimated_duration_days, expected, delta=0.2)

    def test_87_calibrate_success_with_poor_accuracy(self):
        self._seed(count=5, success=False, duration_error=0.2)
        p = _make_prediction(dur=10, sp=0.9)
        result = self._cal.calibrate(p, "build", ["mvp", "safe"])
        # calibration_accuracy = 0.0 (all failed, but predicted 0.8 success)
        # blend = min(5 * 0.1, 0.5) = 0.5
        # corrected = 0.9 * 0.5 + 0.5 * 0.5 = 0.7
        self.assertLess(result.success_probability, 0.9)
        self.assertAlmostEqual(result.success_probability, 0.7, places=1)

    def test_88_calibrate_confidence_with_high_accuracy(self):
        self._seed(count=3, success=True, duration_error=0.1)
        p = _make_prediction(dur=10, sp=0.9, conf=0.5)
        result = self._cal.calibrate(p, "build", ["mvp", "safe"])
        self.assertGreater(result.confidence, 0.5)

    def test_89_calibrate_confidence_with_low_accuracy(self):
        self._seed(count=5, success=False, duration_error=0.2)
        p = _make_prediction(dur=10, sp=0.9, conf=0.5)
        result = self._cal.calibrate(p, "build", ["mvp", "safe"])
        self.assertLess(result.confidence, 0.5)

    def test_90_calibrate_risk_with_high_variance(self):
        self._store.clear()
        p = _make_prediction(dur=10, sp=0.8)
        # Use errors [0.0, 0.0, 0.8, 0.8] → std ~ 0.46 > 0.3 threshold
        for i, err in enumerate([0.0, 0.0, 0.8, 0.8]):
            s = Strategy(name=f"S{i}", description="Test", goal="Build app",
                         tags=[StrategyTag.MVP], prediction=p)
            d = StrategyDecision(
                decision_id=f"sd_var_{i}", goal="Build app",
                timestamp=datetime.utcnow(),
                strategies_considered=[s], chosen_strategy=s, confidence=0.8,
                actual_success=True, actual_duration_days=10 * (1 + err),
            )
            self._store.record(d, "build", True, 10 * (1 + err))

        p2 = _make_prediction(dur=10, sp=0.8, risk=0.3)
        result = self._cal.calibrate(p2, "build", ["mvp"])
        # high variance should increase risk estimate
        self.assertGreater(result.estimated_risk, 0.3)

    def test_91_calibrate_prefers_narrow_over_broad(self):
        # Build records with different bias
        for i in range(3):
            p = _make_prediction(dur=10, sp=0.8)
            s = Strategy(name=f"S{i}", description="Test", goal="Build app",
                         tags=[StrategyTag.MVP], prediction=p)
            d = StrategyDecision(
                decision_id=f"sd_narrow_{i}", goal="Build app",
                timestamp=datetime.utcnow(),
                strategies_considered=[s], chosen_strategy=s, confidence=0.8,
                actual_success=True, actual_duration_days=13.0,  # 30% bias
            )
            self._store.record(d, "build", True, 13.0)

        # Research records with opposite bias
        for i in range(5):
            p = _make_prediction(dur=3, sp=0.9)
            tags = [StrategyTag.SAFE]
            s = Strategy(name=f"R{i}", description="Test", goal="Research",
                         tags=tags, prediction=p)
            d = StrategyDecision(
                decision_id=f"sd_broad_{i}", goal="Research",
                timestamp=datetime.utcnow(),
                strategies_considered=[s], chosen_strategy=s, confidence=0.8,
                actual_success=True, actual_duration_days=2.1,  # -30% bias
            )
            self._store.record(d, "research", True, 2.1)

        # Predict a build MVP strategy — should use narrow build+MVP evidence
        p = _make_prediction(dur=10, sp=0.8)
        result = self._cal.calibrate(p, "build", ["mvp"])
        # Build MVP bias = +0.3 → correction 1.15
        expected = 10 * 1.15
        self.assertAlmostEqual(result.estimated_duration_days, expected, delta=0.2)

    def test_92_record_outcome_creates_record(self):
        p = _make_prediction(dur=10, sp=0.8)
        d = _make_decision("sd_rec_001", prediction=p)
        r = self._cal.record_outcome(d, "build", True, 13.0)
        self.assertIsNotNone(r)
        self.assertEqual(r.decision_id, "sd_rec_001")
        self.assertAlmostEqual(r.duration_error, 0.3)

    def test_93_record_outcome_without_data_returns_none(self):
        d = _make_decision("sd_rec_002", prediction=None)
        r = self._cal.record_outcome(d, "build")
        self.assertIsNone(r)

    def test_94_record_outcome_updates_store(self):
        p = _make_prediction(dur=10, sp=0.8)
        d = _make_decision("sd_rec_003", prediction=p,
                           actual_success=True, actual_duration=12.0)
        self._cal.record_outcome(d, "build", True, 12.0)
        self.assertEqual(self._store.record_count(), 1)

    def test_95_recalibrate_records_and_returns_adjusted(self):
        self._seed(count=3, duration_error=0.3)
        p = _make_prediction(dur=10, sp=0.8)
        d = _make_decision("sd_recal_001", prediction=p,
                           actual_success=True, actual_duration=13.0)
        result = self._cal.recalibrate(d, "build", True, 13.0)
        self.assertIsNotNone(result)
        self.assertEqual(self._store.record_count(), 4)  # 3 seeded + 1 new
        # Duration should be adjusted upward
        self.assertGreater(result.estimated_duration_days, 10.0)

    def test_96_calibrate_does_not_mutate_original(self):
        self._seed(count=3, duration_error=0.3)
        p = _make_prediction(dur=10, sp=0.8)
        original_dur = p.estimated_duration_days
        result = self._cal.calibrate(p, "build", ["mvp", "safe"])
        self.assertEqual(p.estimated_duration_days, original_dur)
        self.assertNotEqual(result.estimated_duration_days, original_dur)

    def test_97_calibrate_with_min_evidence_at_threshold(self):
        self._seed(count=2, duration_error=0.3)
        p = _make_prediction(dur=10, sp=0.8)
        result = self._cal.calibrate(p, "build", ["mvp", "safe"])
        # 2 records < MIN_EVIDENCE_FOR_CALIBRATION (3)
        self.assertEqual(result.estimated_duration_days, p.estimated_duration_days)

    def test_98_calibrate_with_exact_threshold(self):
        self._seed(count=3, duration_error=0.3)
        p = _make_prediction(dur=10, sp=0.8)
        result = self._cal.calibrate(p, "build", ["mvp", "safe"])
        self.assertGreater(result.estimated_duration_days, p.estimated_duration_days)

    def test_99_full_pipeline_with_calibration(self):
        goal = "Build a coffee shop app"
        gen = StrategyGenerator()
        pred = OutcomePredictor()
        eval = StrategyEvaluator()
        sel = StrategySelector()
        cal = PredictionCalibrator()

        # Seed calibration data — build estimates are 30% low
        for i in range(5):
            sp = _make_prediction(dur=10, sp=0.8)
            s = Strategy(name=f"past_{i}", description="", goal="Build app",
                         tags=[StrategyTag.MVP], prediction=sp)
            d = StrategyDecision(
                decision_id=f"sd_hist_{i}", goal="Build app",
                timestamp=datetime.utcnow(),
                strategies_considered=[s], chosen_strategy=s, confidence=0.8,
                actual_success=True, actual_duration_days=13.0,
            )
            cal.store.record(d, "build", True, 13.0)

        strategies = gen.generate(goal)
        pred.predict_all(strategies, calibrator=cal)

        for s in strategies:
            self.assertIsNotNone(s.prediction)
            if StrategyTag.MVP in s.tags:
                # MVP should have duration adjusted upward
                self.assertGreater(s.prediction.estimated_duration_days, 6.0)

        chosen, decision = sel.select(strategies)
        self.assertIsNotNone(chosen)
        self.assertIsNotNone(decision)


# ─── Phase 12.5 — Historical Evidence & Blending ──────────────────────


class _MockKnowledgeStore:
    """Mock KnowledgeStore for testing MemoryAdapter."""

    def __init__(self, experiences=None, knowledge_items=None):
        self._experiences = experiences or []
        self._knowledge_items = knowledge_items or []

    def get_experiences_by_domain(self, domain, limit=20):
        return [e for e in self._experiences if e.domain == domain][:limit]

    def query_knowledge(self, query):
        return [k for k in self._knowledge_items
                if k.category == query.category][:query.limit]

    def search_knowledge(self, text, limit=20):
        return [k for k in self._knowledge_items
                if text in " ".join(k.tags)][:limit]


class _MockActivityStore:
    """Mock ActivityStore for testing MemoryAdapter."""

    def __init__(self, nodes=None):
        self._nodes = nodes or []

    def search_nodes(self, query, limit=10):
        return [n for n in self._nodes
                if query.lower() in n.label.lower()][:limit]


class _MockFactStore:
    """Mock FactStore for testing MemoryAdapter."""

    def __init__(self, facts=None):
        self._facts = facts or []

    def search_facts(self, query, limit=5):
        return [f for f in self._facts
                if query.lower() in f.claim.lower()][:limit]


def _make_exp(goal="Build android app", domain="android",
              duration_days=14, success=True) -> "ExperienceSummary":
    from core.long_term_memory.models import ExperienceSummary
    from uuid import uuid4
    return ExperienceSummary(
        activity_id=f"act_{uuid4().hex[:8]}",
        goal=goal, domain=domain, status="COMPLETED" if success else "FAILED",
        node_count=10, success=success,
        duration_seconds=duration_days * 86400 if duration_days else None,
    )


def _make_act_node(label="Build android app", status="COMPLETED",
                   duration_days=14) -> "ActivityNode":
    from core.activity.models import ActivityNode, ActivityStatus
    from datetime import timedelta
    from uuid import uuid4
    now = datetime.utcnow()
    return ActivityNode(
        node_id=f"n_{uuid4().hex[:8]}",
        activity_id=f"act_{uuid4().hex[:8]}",
        node_type="goal", label=label,
        status=ActivityStatus(status),
        started_at=now - timedelta(days=duration_days),
        completed_at=now,
    )


def _make_knowledge(category="warning", claim="Payment underestimated",
                    tags=None, confidence=0.5):
    from core.long_term_memory.models import KnowledgeItem
    from uuid import uuid4
    return KnowledgeItem(
        knowledge_id=f"k_{uuid4().hex[:8]}",
        category=category, claim=claim,
        tags=tags or [], confidence=confidence,
    )


class TestEvidenceBundle(TestCase):
    """EvidenceBundle data model."""

    def test_100_creation_with_defaults(self):
        b = EvidenceBundle()
        self.assertEqual(b.sample_size, 0)
        self.assertEqual(b.confidence, 0.0)

    def test_101_to_dict(self):
        b = EvidenceBundle(
            sample_size=10, avg_duration_days=15.0,
            duration_std=3.5, success_rate=0.8,
            avg_similarity=0.75,
            common_failures=["auth"],
            similar_activities=["Build app"],
            confidence=0.5,
        )
        d = b.to_dict()
        self.assertEqual(d["sample_size"], 10)
        self.assertIn("success_rate", d)
        self.assertIn("avg_duration_days", d)
        self.assertIn("avg_similarity", d)
        self.assertEqual(d["avg_similarity"], 0.75)


class TestMemoryAdapterEvidence(TestCase):
    """MemoryAdapter with mocked stores."""

    def _adapter(self, experiences=None, activities=None,
                 knowledge=None, facts=None):
        ks = _MockKnowledgeStore(
            experiences=experiences or [],
            knowledge_items=knowledge or [],
        )
        act = _MockActivityStore(nodes=activities or [])
        fs = _MockFactStore(facts=facts or [])
        return MemoryAdapter(activity_store=act, knowledge_store=ks,
                             fact_store=fs)

    def test_110_get_evidence_empty_stores(self):
        adapter = self._adapter()
        bundle = adapter.get_evidence("Build a coffee shop app")
        self.assertEqual(bundle.sample_size, 0)
        self.assertEqual(bundle.confidence, 0.0)

    def test_111_get_evidence_with_experiences(self):
        exps = [
            _make_exp("Build android app", "android", 14, True),
            _make_exp("Build android game", "android", 18, True),
            _make_exp("Build android tool", "android", 10, False),
        ]
        adapter = self._adapter(experiences=exps)
        bundle = adapter.get_evidence("Build android coffee shop app")
        self.assertEqual(bundle.sample_size, 3)
        self.assertGreater(bundle.avg_duration_days, 0)
        self.assertAlmostEqual(bundle.success_rate, 2 / 3, places=2)

    def test_112_get_evidence_confidence_scales_with_size(self):
        adapter_small = self._adapter(
            experiences=[_make_exp() for _ in range(3)]
        )
        adapter_large = self._adapter(
            experiences=[_make_exp() for _ in range(20)]
        )
        small = adapter_small.get_evidence("Build android app")
        large = adapter_large.get_evidence("Build android app")
        self.assertGreater(large.confidence, small.confidence)

    def test_113_get_evidence_includes_similar_activities(self):
        exps = [
            _make_exp("Build android app", "android", 14, True),
            _make_exp("Build android game", "android", 18, True),
        ]
        adapter = self._adapter(experiences=exps)
        bundle = adapter.get_evidence("Build android app")
        self.assertGreater(len(bundle.similar_activities), 0)

    def test_114_get_evidence_with_activity_nodes(self):
        nodes = [
            _make_act_node("Build android app", "COMPLETED", 14),
            _make_act_node("Build web app", "COMPLETED", 10),
            _make_act_node("Build android game", "FAILED", 20),
        ]
        adapter = self._adapter(activities=nodes)
        bundle = adapter.get_evidence("Build android app")
        self.assertGreater(bundle.sample_size, 0)

    def test_115_get_evidence_with_failure_patterns(self):
        knowledge = [
            _make_knowledge("warning", "Authentication often underestimated",
                           tags=["android"], confidence=0.7),
            _make_knowledge("warning", "Payment integration risky",
                           tags=["web"], confidence=0.6),
        ]
        adapter = self._adapter(knowledge=knowledge)
        bundle = adapter.get_evidence("Build android coffee shop",
                                       "build", ["mvp"])
        self.assertGreater(len(bundle.common_failures), 0)
        self.assertIn("Authentication", bundle.common_failures[0])

    def test_116_get_evidence_excludes_other_domain_failures(self):
        knowledge = [
            _make_knowledge("warning", "Android warning",
                           tags=["android"]),
            _make_knowledge("warning", "Web warning",
                           tags=["web"]),
        ]
        adapter = self._adapter(knowledge=knowledge)
        bundle = adapter.get_evidence("Build android app")
        self.assertEqual(len(bundle.common_failures), 1)
        self.assertIn("Android", bundle.common_failures[0])

    def test_117_get_evidence_sample_size_accumulates(self):
        exps = [_make_exp(domain="android") for _ in range(5)]
        nodes = [_make_act_node("Build android", duration_days=10)
                 for _ in range(3)]
        adapter = self._adapter(experiences=exps, activities=nodes)
        bundle = adapter.get_evidence("Build android app")
        self.assertGreaterEqual(bundle.sample_size, 5)

    def test_118_query_similar_activities_with_data(self):
        nodes = [
            _make_act_node("Build android app", "COMPLETED", 14),
            _make_act_node("Build android game", "FAILED", 20),
        ]
        adapter = self._adapter(activities=nodes)
        results = adapter.query_similar_activities("Build android app")
        self.assertGreater(len(results), 0)
        self.assertIn(results[0].goal, ["Build android app",
                                         "Build android game"])

    def test_119_query_domain_evidence_with_data(self):
        exps = [
            _make_exp("Build android app", "android", 14, True),
            _make_exp("Build android tool", "android", 10, False),
        ]
        adapter = self._adapter(experiences=exps)
        results = adapter.query_domain_evidence(["android"])
        self.assertGreater(len(results), 0)
        self.assertAlmostEqual(results[0].success_rate, 0.5, places=1)

    def test_120_query_research_facts_with_data(self):
        from core.research.models import Fact
        from uuid import uuid4
        facts = [
            Fact(fact_id=f"f_{uuid4().hex[:8]}",
                 source_url="https://example.com",
                 claim="Android apps use Kotlin",
                 category="tech"),
            Fact(fact_id=f"f_{uuid4().hex[:8]}",
                 source_url="https://example.com",
                 claim="Coffee shop apps need payment",
                 category="tech"),
        ]
        adapter = self._adapter(facts=facts)
        results = adapter.query_research_facts("coffee shop")
        self.assertGreater(len(results), 0)
        self.assertIn("payment", results[0].lower())

    def test_121_error_tolerance_store_exception(self):
        class BrokenStore:
            def get_experiences_by_domain(self, domain, limit=20):
                raise RuntimeError("DB down")
            def search_knowledge(self, text, limit=20):
                return []
            def query_knowledge(self, query):
                return []

        adapter = MemoryAdapter(
            knowledge_store=BrokenStore(),
            activity_store=_MockActivityStore(),
            fact_store=_MockFactStore(),
        )
        bundle = adapter.get_evidence("Build android app")
        self.assertEqual(bundle.sample_size, 0)


class TestSimilarityScorer(TestCase):
    """SimilarityScorer — Phase 12.6 goal-activity similarity."""

    def _make_exp(self, goal="Build android app", domain="android",
                  duration_days=14, success=True, tools=None):
        return _make_exp(goal, domain, duration_days, success)

    def test_140_identical_goals_score_near_max(self):
        from core.strategy.similarity import SimilarityScorer
        scorer = SimilarityScorer()
        exp = self._make_exp("Build android app", "android", 14, True)
        score = scorer.score_experience("Build android app", "build", [], exp)
        self.assertGreater(score, 0.70)

    def test_141_different_goal_type_penalizes(self):
        from core.strategy.similarity import SimilarityScorer
        scorer = SimilarityScorer()
        exp = self._make_exp("Research android architecture", "android", 5, True)
        score = scorer.score_experience("Build android app", "build", [], exp)
        # research vs build → goal_type mismatch (0 → loses 0.40)
        self.assertLess(score, 0.50)

    def test_142_tag_overlap_boosts_score(self):
        from core.strategy.similarity import SimilarityScorer
        from core.long_term_memory.models import ExperienceSummary
        from uuid import uuid4
        exp = ExperienceSummary(
            activity_id=f"act_{uuid4().hex[:8]}",
            goal="Build android app", domain="android",
            status="COMPLETED", node_count=10, success=True,
            tools_used=["mvp", "fast", "android"],
            duration_seconds=14 * 86400,
        )
        scorer = SimilarityScorer()
        score_no_tags = scorer.score_experience("Build android app", "build", [], exp)
        score_with_tags = scorer.score_experience("Build android app", "build",
                                                   ["mvp", "fast"], exp)
        self.assertGreater(score_with_tags, score_no_tags)

    def test_143_domain_mismatch_penalizes(self):
        from core.strategy.similarity import SimilarityScorer
        exp = self._make_exp("Build web app", "web", 14, True)
        scorer = SimilarityScorer()
        score = scorer.score_experience("Build android app", "build", [], exp)
        # web vs android → domain mismatch
        self.assertLess(score, 0.60)

    def test_144_filter_and_score_returns_sorted(self):
        from core.strategy.similarity import SimilarityScorer
        exps = [
            self._make_exp("Build android app", "android", 14, True),
            self._make_exp("Research web architecture", "web", 5, True),
            self._make_exp("Refactor iOS module", "general", 7, True),
        ]
        scorer = SimilarityScorer()
        scored = scorer.filter_and_score(exps, "Build android coffee shop",
                                          "build", [])
        self.assertGreater(len(scored), 0)
        # First result should be most similar (build/android)
        self.assertEqual(scored[0][1].goal, "Build android app")

    def test_145_filter_excludes_below_threshold(self):
        from core.strategy.similarity import SimilarityScorer
        exps = [
            self._make_exp("Research quantum computing", "general", 10, True),
            self._make_exp("Build android app", "android", 14, True),
        ]
        scorer = SimilarityScorer()
        scored = scorer.filter_and_score(exps, "Build android coffee shop",
                                          "build", [])
        self.assertEqual(len(scored), 1)
        self.assertEqual(scored[0][1].goal, "Build android app")

    def test_146_filter_respects_max_results(self):
        from core.strategy.similarity import SimilarityScorer, MAX_RESULTS
        exps = [self._make_exp(f"Build android app {i}", "android", 14, True)
                for i in range(30)]
        scorer = SimilarityScorer()
        scored = scorer.filter_and_score(exps, "Build android app", "build", [])
        self.assertLessEqual(len(scored), MAX_RESULTS)

    def test_147_filter_empty_returns_empty(self):
        from core.strategy.similarity import SimilarityScorer
        scorer = SimilarityScorer()
        scored = scorer.filter_and_score([], "Build android app", "build", [])
        self.assertEqual(len(scored), 0)

    def test_148_avg_similarity_in_bundle(self):
        exps = [
            _make_exp("Build android app", "android", 14, True),
            _make_exp("Build android game", "android", 18, True),
        ]
        adapter = MemoryAdapter(
            knowledge_store=_MockKnowledgeStore(experiences=exps),
            activity_store=_MockActivityStore(),
            fact_store=_MockFactStore(),
        )
        bundle = adapter.get_evidence("Build android coffee shop")
        self.assertGreater(bundle.avg_similarity, 0)
        self.assertLessEqual(bundle.avg_similarity, 1.0)

    def test_149_different_goal_type_activities_excluded(self):
        exps = [
            _make_exp("Build android app", "android", 14, True),
            _make_exp("Research machine learning", "ml", 5, True),
            _make_exp("Refactor web backend", "web", 7, False),
        ]
        adapter = MemoryAdapter(
            knowledge_store=_MockKnowledgeStore(experiences=exps),
            activity_store=_MockActivityStore(),
            fact_store=_MockFactStore(),
        )
        bundle = adapter.get_evidence("Build android coffee shop", "build", [])
        # research and refactor experiences should be filtered out by similarity
        # all remaining experiences should be build/android
        self.assertGreaterEqual(bundle.sample_size, 1)
        for act in bundle.similar_activities:
            self.assertIn("Build", act)

    def test_150_avg_similarity_empty_returns_zero(self):
        adapter = MemoryAdapter(
            knowledge_store=_MockKnowledgeStore(experiences=[]),
            activity_store=_MockActivityStore(),
            fact_store=_MockFactStore(),
        )
        bundle = adapter.get_evidence("Build android app")
        self.assertEqual(bundle.avg_similarity, 0)


class TestPredictorBlending(TestCase):
    """OutcomePredictor._blend with EvidenceBundle."""

    def setUp(self):
        self._pred = OutcomePredictor()

    def test_130_blend_no_evidence_returns_heuristic(self):
        h = _make_prediction(dur=14, sp=0.75)
        e = EvidenceBundle()
        result = self._pred._blend(h, e)
        self.assertEqual(result.estimated_duration_days,
                         h.estimated_duration_days)
        self.assertEqual(result.success_probability,
                         h.success_probability)

    def test_131_blend_with_evidence_blends_correctly(self):
        h = _make_prediction(dur=14, sp=0.75)
        e = EvidenceBundle(
            sample_size=10, avg_duration_days=18.0,
            success_rate=0.6, confidence=0.5,
        )
        result = self._pred._blend(h, e)
        # weight = min(10/20, 1.0) = 0.5
        # duration = 14 * 0.5 + 18 * 0.5 = 16.0
        self.assertAlmostEqual(result.estimated_duration_days, 16.0,
                               delta=0.1)
        # success = 0.75 * 0.5 + 0.6 * 0.5 = 0.675
        self.assertAlmostEqual(result.success_probability, 0.675,
                               places=2)

    def test_132_blend_weight_scales_with_sample_size(self):
        h = _make_prediction(dur=14, sp=0.75)
        low = EvidenceBundle(sample_size=2, avg_duration_days=20.0,
                              success_rate=0.5, confidence=0.1)
        high = EvidenceBundle(sample_size=20, avg_duration_days=20.0,
                               success_rate=0.5, confidence=0.9)
        r_low = self._pred._blend(h, low)
        r_high = self._pred._blend(h, high)
        self.assertGreater(
            abs(r_high.estimated_duration_days - 14.0),
            abs(r_low.estimated_duration_days - 14.0),
        )

    def test_133_blend_updates_evidence_count(self):
        h = _make_prediction(dur=14, sp=0.75, evidence=3)
        e = EvidenceBundle(sample_size=7, avg_duration_days=18.0,
                            success_rate=0.6, confidence=0.5)
        result = self._pred._blend(h, e)
        self.assertEqual(result.evidence_count, 3 + 7)

    def test_134_blend_updates_confidence(self):
        h = _make_prediction(dur=14, sp=0.75, conf=0.3)
        e = EvidenceBundle(sample_size=20, avg_duration_days=18.0,
                            success_rate=0.6, confidence=0.9)
        result = self._pred._blend(h, e)
        self.assertGreater(result.confidence, 0.3)

    def test_135_predict_with_memory_adapter(self):
        exps = [
            _make_exp("Build android app", "android", 16, True),
            _make_exp("Build android game", "android", 20, True),
        ]
        adapter = MemoryAdapter(
            knowledge_store=_MockKnowledgeStore(experiences=exps),
            activity_store=_MockActivityStore(),
            fact_store=_MockFactStore(),
        )
        strategy = Strategy(
            name="MVP-first", description="",
            goal="Build android coffee shop app",
            tags=[StrategyTag.MVP],
        )
        result = self._pred.predict(strategy, "build",
                                     memory_adapter=adapter)
        self.assertIsNotNone(result)
        self.assertGreater(result.evidence_count, 0)

    def test_136_predict_all_with_memory_adapter(self):
        exps = [_make_exp("Build android app", "android", 15, True)]
        adapter = MemoryAdapter(
            knowledge_store=_MockKnowledgeStore(experiences=exps),
            activity_store=_MockActivityStore(),
            fact_store=_MockFactStore(),
        )
        strategies = [
            Strategy(name="MVP-first", description="",
                     goal="Build android app", tags=[StrategyTag.MVP]),
            Strategy(name="Quality-first", description="",
                     goal="Build android app",
                     tags=[StrategyTag.QUALITY_FIRST]),
        ]
        results = self._pred.predict_all(strategies, "build",
                                          memory_adapter=adapter)
        for s in results:
            self.assertIsNotNone(s.prediction)
            self.assertGreater(s.prediction.evidence_count, 0)

    def test_137_full_pipeline_with_evidence(self):
        goal = "Build android coffee shop app"
        exps = [
            _make_exp("Build android app", "android", 18, True),
            _make_exp("Build android game", "android", 22, True),
        ]
        adapter = MemoryAdapter(
            knowledge_store=_MockKnowledgeStore(experiences=exps),
            activity_store=_MockActivityStore(),
            fact_store=_MockFactStore(),
        )

        gen = StrategyGenerator()
        pred = OutcomePredictor()
        eval = StrategyEvaluator()
        sel = StrategySelector()

        strategies = gen.generate(goal)
        pred.predict_all(strategies, "build", memory_adapter=adapter)

        for s in strategies:
            self.assertIsNotNone(s.prediction)
            if s.prediction:
                self.assertGreater(s.prediction.evidence_count, 0)

        ordered = eval.ordered(strategies)
        self.assertEqual(len(ordered), len(strategies))

        chosen, decision = sel.select(strategies)
        self.assertIsNotNone(chosen)
        self.assertIsNotNone(decision)

    def test_138_predict_with_both_adapter_and_calibrator(self):
        from core.strategy.calibration import PredictionCalibrator

        cal = PredictionCalibrator()
        for i in range(5):
            sp = _make_prediction(dur=10, sp=0.8)
            s = Strategy(name=f"past_{i}", description="", goal="Build app",
                         tags=[StrategyTag.MVP], prediction=sp)
            d = StrategyDecision(
                decision_id=f"sd_cal_{i}", goal="Build app",
                timestamp=datetime.utcnow(),
                strategies_considered=[s], chosen_strategy=s, confidence=0.8,
                actual_success=True, actual_duration_days=14.0,
            )
            cal.store.record(d, "build", True, 14.0)

        exps = [_make_exp("Build android app", "android", 16, True)]
        adapter = MemoryAdapter(
            knowledge_store=_MockKnowledgeStore(experiences=exps),
            activity_store=_MockActivityStore(),
            fact_store=_MockFactStore(),
        )

        strategy = Strategy(
            name="MVP-first", description="",
            goal="Build android coffee shop app",
            tags=[StrategyTag.MVP],
        )
        result = self._pred.predict(strategy, "build",
                                     calibrator=cal,
                                     memory_adapter=adapter)
        self.assertIsNotNone(result)
        self.assertGreater(result.evidence_count, 0)
