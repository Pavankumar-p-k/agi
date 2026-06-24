"""Opportunity Forecasting tests — Phase 21.

Covers:
  - HistoricalDataPoint model
  - ForecastedOpportunity model
  - ForecastResult aggregate
  - Trend analysis (velocity, direction)
  - Velocity estimation without history
  - Core forecasting formula
  - Confidence computation
  - Horizon classification (short/medium/long)
  - Rationale building
  - Evidence collection
  - Integration with OpportunityGraph + Bottlenecks
  - Edge cases: empty inputs, single system, no history
  - History collection from OpportunityStore
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from core.opportunity.bottlenecks import Bottleneck
from core.opportunity.forecasting import (
    BOTTLENECK_WEIGHT,
    DEFAULT_VELOCITY,
    ForecastHorizon,
    ForecastResult,
    ForecastTrend,
    ForecastedOpportunity,
    ForecastingEngine,
    HistoricalDataPoint,
    UNLOCK_WEIGHT,
)
from core.opportunity.graph import (
    OpportunityGraph,
    OpportunityGraphEdge,
    build_default_graph,
)
from core.opportunity.models import Opportunity, OpportunitySource, OpportunityStatus


# ── Model Tests ───────────────────────────────────────────────────────


class TestHistoricalDataPoint(unittest.TestCase):

    def test_10_default_source(self):
        dp = HistoricalDataPoint("2026-01-01", 0.5)
        self.assertEqual(dp.timestamp, "2026-01-01")
        self.assertAlmostEqual(dp.opportunity_score, 0.5)
        self.assertEqual(dp.source, "unknown")

    def test_11_to_dict(self):
        dp = HistoricalDataPoint("2026-06-01T00:00:00", 0.75, "calibration")
        d = dp.to_dict()
        self.assertEqual(d["timestamp"], "2026-06-01T00:00:00")
        self.assertAlmostEqual(d["score"], 0.750)
        self.assertEqual(d["source"], "calibration")


class TestForecastedOpportunity(unittest.TestCase):

    def test_20_defaults(self):
        f = ForecastedOpportunity("browser", 0.5, 0.55)
        self.assertEqual(f.target_system, "browser")
        self.assertAlmostEqual(f.current_score, 0.5)
        self.assertAlmostEqual(f.predicted_score, 0.55)
        self.assertEqual(f.horizon, ForecastHorizon.MEDIUM_TERM)
        self.assertEqual(f.trend, ForecastTrend.STABLE)
        self.assertAlmostEqual(f.velocity, 0.0)
        self.assertAlmostEqual(f.unlock_value, 1.0)
        self.assertAlmostEqual(f.bottleneck_pressure, 0.0)

    def test_21_to_dict(self):
        f = ForecastedOpportunity(
            "self_modification", 0.35, 0.42, confidence=0.78,
            horizon=ForecastHorizon.SHORT_TERM, trend=ForecastTrend.DECLINING,
            velocity=-0.025, unlock_value=2.1, bottleneck_pressure=0.45,
            rationale="Declining scores suggest urgency.",
        )
        d = f.to_dict()
        self.assertEqual(d["system"], "self_modification")
        self.assertAlmostEqual(d["current_score"], 0.350)
        self.assertAlmostEqual(d["predicted_score"], 0.420)
        self.assertAlmostEqual(d["confidence"], 0.780)
        self.assertEqual(d["horizon"], "short_term")
        self.assertEqual(d["trend"], "declining")
        self.assertAlmostEqual(d["velocity"], -0.0250)
        self.assertAlmostEqual(d["unlock_value"], 2.100)
        self.assertAlmostEqual(d["bottleneck_pressure"], 0.450)


class TestForecastResult(unittest.TestCase):

    def test_30_empty(self):
        result = ForecastResult()
        self.assertEqual(result.forecasts, [])
        self.assertEqual(result.total_systems, 0)
        self.assertAlmostEqual(result.average_confidence, 0.0)

    def test_31_with_forecasts(self):
        forecasts = [
            ForecastedOpportunity("A", 0.5, 0.6, confidence=0.9),
            ForecastedOpportunity("B", 0.3, 0.4, confidence=0.5),
        ]
        result = ForecastResult(
            forecasts=forecasts,
            generated_at=datetime.now(timezone.utc),
            total_systems=2,
            average_confidence=0.7,
        )
        self.assertEqual(len(result.forecasts), 2)
        self.assertAlmostEqual(result.average_confidence, 0.7)

    def test_32_top_n(self):
        forecasts = [
            ForecastedOpportunity("low", 0.1, 0.12, confidence=0.5),
            ForecastedOpportunity("mid", 0.5, 0.52, confidence=0.7),
            ForecastedOpportunity("high", 0.9, 0.91, confidence=0.9),
        ]
        result = ForecastResult(forecasts=forecasts)
        top2 = result.top(2)
        self.assertEqual(len(top2), 2)
        self.assertEqual(top2[0].target_system, "high")
        self.assertEqual(top2[1].target_system, "mid")

    def test_33_to_dict(self):
        forecasts = [ForecastedOpportunity("A", 0.5, 0.6)]
        result = ForecastResult(
            forecasts=forecasts,
            generated_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
            total_systems=1,
            average_confidence=0.5,
        )
        d = result.to_dict()
        self.assertEqual(len(d["forecasts"]), 1)
        self.assertIsNotNone(d["generated_at"])
        self.assertEqual(d["total_systems"], 1)


# ── Trend Analysis Tests ──────────────────────────────────────────────


class TestTrendAnalysis(unittest.TestCase):

    def setUp(self):
        self.engine = ForecastingEngine()

    def test_40_no_history_is_stable(self):
        v, t = self.engine._compute_trend([])
        self.assertAlmostEqual(v, DEFAULT_VELOCITY)
        self.assertEqual(t, ForecastTrend.STABLE)

    def test_41_single_point_is_stable(self):
        v, t = self.engine._compute_trend([
            HistoricalDataPoint("2026-01-01", 0.5),
        ])
        self.assertAlmostEqual(v, DEFAULT_VELOCITY)
        self.assertEqual(t, ForecastTrend.STABLE)

    def test_42_declining_trend(self):
        v, t = self.engine._compute_trend([
            HistoricalDataPoint("2026-01-01", 0.8),
            HistoricalDataPoint("2026-02-01", 0.7),
            HistoricalDataPoint("2026-03-01", 0.6),
        ])
        self.assertEqual(t, ForecastTrend.DECLINING)

    def test_43_improving_trend(self):
        v, t = self.engine._compute_trend([
            HistoricalDataPoint("2026-01-01", 0.3),
            HistoricalDataPoint("2026-02-01", 0.4),
            HistoricalDataPoint("2026-03-01", 0.6),
        ])
        self.assertEqual(t, ForecastTrend.IMPROVING)

    def test_44_stable_trend(self):
        v, t = self.engine._compute_trend([
            HistoricalDataPoint("2026-01-01", 0.5),
            HistoricalDataPoint("2026-02-01", 0.51),
            HistoricalDataPoint("2026-03-01", 0.49),
        ])
        self.assertEqual(t, ForecastTrend.STABLE)

    def test_45_velocity_magnitude_reasonable(self):
        """Declining from 0.8 to 0.2 over 3 steps → velocity ~ -0.3."""
        v, t = self.engine._compute_trend([
            HistoricalDataPoint("2026-01-01", 0.8),
            HistoricalDataPoint("2026-02-01", 0.5),
            HistoricalDataPoint("2026-03-01", 0.2),
        ])
        self.assertEqual(t, ForecastTrend.DECLINING)
        self.assertAlmostEqual(v, -0.3, places=2)


# ── Velocity Estimation Tests ─────────────────────────────────────────


class TestVelocityEstimation(unittest.TestCase):

    def setUp(self):
        self.engine = ForecastingEngine()

    def test_50_default_when_no_signals(self):
        v, t = self.engine._estimate_velocity(0.5, 1.0, 0.0)
        self.assertAlmostEqual(v, DEFAULT_VELOCITY)
        self.assertEqual(t, ForecastTrend.STABLE)

    def test_51_high_bottleneck_high_unlock_suggests_declining(self):
        v, t = self.engine._estimate_velocity(0.3, 2.0, 0.5)
        self.assertEqual(t, ForecastTrend.DECLINING)
        self.assertLess(v, 0)

    def test_52_high_score_low_unlock_suggests_stable(self):
        v, t = self.engine._estimate_velocity(0.7, 1.1, 0.0)
        self.assertIn(t, [ForecastTrend.STABLE, ForecastTrend.IMPROVING])
        self.assertGreaterEqual(v, 0)


# ── Forecasting Formula Tests ─────────────────────────────────────────


class TestForecastingFormula(unittest.TestCase):

    def setUp(self):
        self.engine = ForecastingEngine()

    def test_60_no_trend_no_bottleneck_returns_current(self):
        predicted, conf = self.engine._compute_forecast(
            current_score=0.5, velocity=0.0, trend=ForecastTrend.STABLE,
            unlock_value=1.0, bottleneck_pressure=0.0, history=[],
        )
        self.assertAlmostEqual(predicted, 0.5, places=2)

    def test_61_declining_trend_increases_prediction(self):
        """Negative velocity means system is worsening → higher opportunity."""
        predicted, conf = self.engine._compute_forecast(
            current_score=0.5, velocity=-0.1, trend=ForecastTrend.DECLINING,
            unlock_value=1.0, bottleneck_pressure=0.0, history=[],
        )
        self.assertGreater(predicted, 0.5)

    def test_62_improving_trend_decreases_prediction(self):
        """Positive velocity means system is improving → lower opportunity."""
        predicted, conf = self.engine._compute_forecast(
            current_score=0.5, velocity=0.1, trend=ForecastTrend.IMPROVING,
            unlock_value=1.0, bottleneck_pressure=0.0, history=[],
        )
        self.assertLess(predicted, 0.5)

    def test_63_bottleneck_pressure_boosts_prediction(self):
        no_bn, _ = self.engine._compute_forecast(
            0.5, 0.0, ForecastTrend.STABLE, 1.0, 0.0, [],
        )
        with_bn, _ = self.engine._compute_forecast(
            0.5, 0.0, ForecastTrend.STABLE, 1.0, 0.8, [],
        )
        self.assertGreater(with_bn, no_bn)

    def test_64_unlock_value_boosts_prediction(self):
        no_ul, _ = self.engine._compute_forecast(
            0.5, 0.0, ForecastTrend.STABLE, 1.0, 0.0, [],
        )
        with_ul, _ = self.engine._compute_forecast(
            0.5, 0.0, ForecastTrend.STABLE, 2.5, 0.0, [],
        )
        self.assertGreater(with_ul, no_ul)

    def test_65_prediction_clamped_to_minimum(self):
        predicted, conf = self.engine._compute_forecast(
            current_score=0.001, velocity=-2.0, trend=ForecastTrend.DECLINING,
            unlock_value=0.5, bottleneck_pressure=-10, history=[],
        )
        self.assertGreaterEqual(predicted, 0.01)

    def test_66_prediction_clamped_to_maximum(self):
        predicted, conf = self.engine._compute_forecast(
            current_score=0.5, velocity=-2.0, trend=ForecastTrend.DECLINING,
            unlock_value=5.0, bottleneck_pressure=10, history=[],
        )
        self.assertLessEqual(predicted, 1.0)

    def test_67_full_formula_reasonable_range(self):
        """Realistic scenario: moderate everything."""
        predicted, conf = self.engine._compute_forecast(
            current_score=0.4, velocity=-0.02, trend=ForecastTrend.DECLINING,
            unlock_value=1.8, bottleneck_pressure=0.35, history=[],
        )
        self.assertGreater(predicted, 0.3)
        self.assertLess(predicted, 0.9)
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 1.0)


# ── Confidence Computation Tests ──────────────────────────────────────


class TestConfidence(unittest.TestCase):

    def setUp(self):
        self.engine = ForecastingEngine()

    def test_70_no_history_minimum_confidence(self):
        conf = self.engine._compute_confidence([], 0.0, 0)
        self.assertAlmostEqual(conf, 0.30, places=2)

    def test_71_some_history_increases_confidence(self):
        conf_low = self.engine._compute_confidence([], 0.0, 0)
        conf_high = self.engine._compute_confidence(
            [HistoricalDataPoint("2026-01-01", 0.5),
             HistoricalDataPoint("2026-02-01", 0.6)], 0.05, 2
        )
        self.assertGreater(conf_high, conf_low)

    def test_72_lots_of_history_plus_trend_high_confidence(self):
        history = [HistoricalDataPoint(f"2026-{m:02d}-01", 0.5 + m * 0.02)
                   for m in range(1, 13)]
        conf = self.engine._compute_confidence(history, 0.02, 12)
        self.assertAlmostEqual(conf, 0.9, places=2)

    def test_73_confidence_capped_at_one(self):
        conf = self.engine._compute_confidence(
            [HistoricalDataPoint(f"2026-{m:02d}-01", 0.5) for m in range(1, 21)],
            0.05, 20
        )
        self.assertLessEqual(conf, 1.0)


# ── Horizon Classification Tests ──────────────────────────────────────


class TestHorizonClassification(unittest.TestCase):

    def setUp(self):
        self.engine = ForecastingEngine()

    def test_80_declining_high_bottleneck_is_short_term(self):
        h = self.engine._classify_horizon(0.3, -0.03, 0.5, 1.0)
        self.assertEqual(h, ForecastHorizon.SHORT_TERM)

    def test_81_high_score_very_high_bottleneck_is_short_term(self):
        h = self.engine._classify_horizon(0.2, 0.0, 0.6, 1.0)
        self.assertEqual(h, ForecastHorizon.SHORT_TERM)

    def test_82_low_score_very_high_unlock_is_long_term(self):
        h = self.engine._classify_horizon(0.04, 0.0, 0.0, 2.5)
        self.assertEqual(h, ForecastHorizon.LONG_TERM)

    def test_83_extreme_unlock_is_long_term(self):
        h = self.engine._classify_horizon(0.3, 0.0, 0.0, 3.5)
        self.assertEqual(h, ForecastHorizon.LONG_TERM)

    def test_84_default_is_medium_term(self):
        h = self.engine._classify_horizon(0.3, 0.0, 0.0, 1.0)
        self.assertEqual(h, ForecastHorizon.MEDIUM_TERM)


# ── Rationale Tests ───────────────────────────────────────────────────


class TestRationale(unittest.TestCase):

    def setUp(self):
        self.engine = ForecastingEngine()

    def test_90_mentions_system_and_scores(self):
        r = self.engine._build_rationale(
            "browser", 0.5, 0.65, 0.0, ForecastTrend.STABLE,
            ForecastHorizon.MEDIUM_TERM, 1.0, 0.0, 0.5,
        )
        self.assertIn("browser", r)
        self.assertIn("0.500", r)
        self.assertIn("0.650", r)

    def test_91_declining_trend_mentioned(self):
        r = self.engine._build_rationale(
            "sys", 0.3, 0.42, -0.05, ForecastTrend.DECLINING,
            ForecastHorizon.SHORT_TERM, 1.0, 0.0, 0.7,
        )
        self.assertIn("Declining", r)

    def test_92_bottleneck_pressure_mentioned_when_high(self):
        r = self.engine._build_rationale(
            "sys", 0.3, 0.45, 0.0, ForecastTrend.STABLE,
            ForecastHorizon.SHORT_TERM, 1.0, 0.6, 0.8,
        )
        self.assertIn("bottleneck", r.lower())

    def test_93_unlock_value_mentioned_when_high(self):
        r = self.engine._build_rationale(
            "sys", 0.3, 0.50, 0.0, ForecastTrend.STABLE,
            ForecastHorizon.LONG_TERM, 2.0, 0.0, 0.6,
        )
        self.assertIn("unlock", r.lower())

    def test_94_horizon_action_included(self):
        r_sh = self.engine._build_rationale(
            "a", 0.3, 0.40, 0.0, ForecastTrend.STABLE,
            ForecastHorizon.SHORT_TERM, 1.0, 0.0, 0.5,
        )
        self.assertIn("Act now", r_sh)

        r_mt = self.engine._build_rationale(
            "a", 0.3, 0.35, 0.0, ForecastTrend.STABLE,
            ForecastHorizon.MEDIUM_TERM, 1.0, 0.0, 0.5,
        )
        self.assertIn("Plan for next cycle", r_mt)

        r_lt = self.engine._build_rationale(
            "a", 0.3, 0.35, 0.0, ForecastTrend.STABLE,
            ForecastHorizon.LONG_TERM, 1.0, 0.0, 0.5,
        )
        self.assertIn("high future potential", r_lt)


# ── Evidence Tests ────────────────────────────────────────────────────


class TestEvidence(unittest.TestCase):

    def setUp(self):
        self.engine = ForecastingEngine()

    def test_100_evidence_includes_history_count(self):
        history = [HistoricalDataPoint("2026-01-01", 0.5),
                   HistoricalDataPoint("2026-02-01", 0.6)]
        ev = self.engine._build_evidence(history, 0.05, 0.0, 1.0)
        self.assertTrue(any("2 historical" in e for e in ev))
        self.assertTrue(any("0.0500" in e for e in ev))

    def test_101_evidence_includes_bottleneck(self):
        ev = self.engine._build_evidence([], 0.0, 0.45, 1.0)
        self.assertTrue(any("0.450" in e for e in ev))

    def test_102_evidence_includes_unlock_value(self):
        ev = self.engine._build_evidence([], 0.0, 0.0, 2.5)
        self.assertTrue(any("2.500" in e for e in ev))

    def test_103_no_history_no_extra_signals(self):
        ev = self.engine._build_evidence([], 0.0, 0.0, 1.0)
        self.assertEqual(ev, [])


# ── Integration Tests ─────────────────────────────────────────────────


class TestIntegration(unittest.TestCase):
    """End-to-end: forecast with real graph + fake opportunities + bottlenecks."""

    def setUp(self):
        self.engine = ForecastingEngine()
        self.graph = build_default_graph()

    def _make_opp(self, system: str, score: float) -> Opportunity:
        return Opportunity(
            id=f"opp_{system}", target_system=system,
            improvement_description=f"Improve {system}",
            source=OpportunitySource.CEILING,
            bottleneck_impact=score * 0.8,
            improvement_headroom=score,
            success_probability=0.5, confidence=0.5,
            calibration_accuracy=1.0,
            opportunity_score=score,
            rationale="test", status=OpportunityStatus.OPEN,
        )

    def test_110_forecast_with_default_graph_produces_all_systems(self):
        """All default graph nodes should receive forecasts."""
        opportunities = [
            self._make_opp(n.system_name, 0.5)
            for n in self.graph.nodes.values()
        ]
        result = self.engine.forecast(opportunities, self.graph)
        self.assertGreater(result.total_systems, 0)
        self.assertGreater(len(result.forecasts), 0)

    def test_111_forecast_sorted_by_predicted_score(self):
        """Forecasts should be returned sorted by predicted_score descending."""
        sysnames = ["self_modification", "opportunity_discovery",
                     "browser_automation", "strategic_reasoning"]
        opps = [self._make_opp(s, 0.3 + i * 0.15) for i, s in enumerate(sysnames)]
        result = self.engine.forecast(opps, self.graph)
        scores = [f.predicted_score for f in result.forecasts]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_112_forecast_with_bottlenecks_integrates_pressure(self):
        """Bottlenecks should influence forecast scores."""
        opps = [self._make_opp("self_modification", 0.4),
                self._make_opp("browser_automation", 0.4)]
        bottlenecks = [
            Bottleneck(
                subsystem="self_modification", local_impact=0.6,
                propagated_impact=0.3, total_constrained_value=0.9,
                confidence=0.8,
            ),
        ]
        result = self.engine.forecast(opps, self.graph, bottlenecks)
        sm = next(f for f in result.forecasts if f.target_system == "self_modification")
        ba = next(f for f in result.forecasts if f.target_system == "browser_automation")
        self.assertGreater(sm.predicted_score, ba.predicted_score)

    def test_113_forecast_returns_confidence_for_each(self):
        opps = [self._make_opp("improvement", 0.5)]
        result = self.engine.forecast(opps, self.graph)
        for f in result.forecasts:
            self.assertGreaterEqual(f.confidence, 0.0)
            self.assertLessEqual(f.confidence, 1.0)

    def test_114_forecast_includes_rationale(self):
        opps = [self._make_opp("execution", 0.5)]
        result = self.engine.forecast(opps, self.graph)
        for f in result.forecasts:
            self.assertTrue(len(f.rationale) > 10)

    def test_115_forecast_with_opportunity_sourced_from_store(self):
        """When history_store is provided, history is collected."""
        mock_store = MagicMock()
        mock_store.list_records.return_value = []
        opps = [self._make_opp("execution_infrastructure", 0.5)]
        result = self.engine.forecast(opps, self.graph, history_store=mock_store)
        self.assertEqual(result.total_systems, 1)
        mock_store.list_records.assert_called_once()

    def test_116_empty_opportunities_returns_empty_result(self):
        result = self.engine.forecast([], self.graph)
        self.assertEqual(result.total_systems, 0)
        self.assertEqual(len(result.forecasts), 0)
        self.assertAlmostEqual(result.average_confidence, 0.0)


# ── Edge Case Tests ───────────────────────────────────────────────────


class TestEdgeCases(unittest.TestCase):

    def setUp(self):
        self.engine = ForecastingEngine()

    def _make_opp(self, system: str, score: float) -> Opportunity:
        return Opportunity(
            id=f"opp_{system}", target_system=system,
            improvement_description=f"Improve {system}",
            source=OpportunitySource.CEILING,
            bottleneck_impact=score * 0.8,
            improvement_headroom=score,
            success_probability=0.5, confidence=0.5,
            calibration_accuracy=1.0,
            opportunity_score=score,
            rationale="test", status=OpportunityStatus.OPEN,
        )

    def test_120_system_not_in_graph_skipped(self):
        graph = OpportunityGraph()
        graph.add_node("only_system")
        opps = [self._make_opp("not_in_graph", 0.5),
                self._make_opp("only_system", 0.5)]
        result = self.engine.forecast(opps, graph)
        names = [f.target_system for f in result.forecasts]
        self.assertNotIn("not_in_graph", names)
        self.assertIn("only_system", names)

    def test_121_single_opportunity_produces_forecast(self):
        graph = OpportunityGraph()
        graph.add_node("lonely")
        opps = [self._make_opp("lonely", 0.5)]
        result = self.engine.forecast(opps, graph)
        self.assertEqual(result.total_systems, 1)
        f = result.forecasts[0]
        self.assertEqual(f.target_system, "lonely")

    def test_122_null_bottlenecks_does_not_crash(self):
        graph = build_default_graph()
        opps = [self._make_opp(n.system_name, 0.5)
                for n in graph.nodes.values()]
        result = self.engine.forecast(opps, graph, bottlenecks=None)
        self.assertGreater(result.total_systems, 0)
        for f in result.forecasts:
            self.assertAlmostEqual(f.bottleneck_pressure, 0.0)

    def test_123_high_bottleneck_high_unlock_produces_sensible_score(self):
        graph = OpportunityGraph()
        graph.add_node("target")
        opps = [self._make_opp("target", 0.5)]
        bottlenecks = [Bottleneck(
            subsystem="target", local_impact=0.8,
            propagated_impact=0.5, total_constrained_value=1.3,
            confidence=0.9,
        )]
        result = self.engine.forecast(opps, graph, bottlenecks)
        f = result.forecasts[0]
        self.assertGreater(f.predicted_score, 0.5)
        self.assertAlmostEqual(f.bottleneck_pressure, 1.3)

    def test_124_min_score_system_still_gets_reasonable_forecast(self):
        graph = OpportunityGraph()
        graph.add_node("tiny")
        opps = [self._make_opp("tiny", 0.01)]
        result = self.engine.forecast(opps, graph)
        self.assertGreaterEqual(result.forecasts[0].predicted_score, 0.01)


# ── History Collection Tests ──────────────────────────────────────────


class TestHistoryCollection(unittest.TestCase):

    def setUp(self):
        self.engine = ForecastingEngine()
        self.graph = build_default_graph()

    def test_130_empty_store_returns_empty_history(self):
        mock = MagicMock()
        mock.list_records.return_value = []
        history = self.engine._collect_history(mock, self.graph)
        self.assertEqual(history, {})

    def test_131_store_records_grouped_by_system(self):
        mock = MagicMock()
        rec1 = MagicMock()
        rec1.target_system = "execution_infrastructure"
        rec1.completed_at = "2026-01-01"
        rec1.selected_at = "2026-01-01"
        rec1.predicted_score = 0.5
        rec1.source = "calibration"
        rec2 = MagicMock()
        rec2.target_system = "execution_infrastructure"
        rec2.completed_at = "2026-02-01"
        rec2.selected_at = "2026-02-01"
        rec2.predicted_score = 0.55
        rec2.source = "calibration"
        rec3 = MagicMock()
        rec3.target_system = "improvement"
        rec3.completed_at = "2026-01-15"
        rec3.selected_at = "2026-01-15"
        rec3.predicted_score = 0.3
        rec3.source = "calibration"
        mock.list_records.return_value = [rec1, rec2, rec3]

        history = self.engine._collect_history(mock, self.graph)
        self.assertIn("execution_infrastructure", history)
        self.assertIn("improvement", history)
        self.assertEqual(len(history["execution_infrastructure"]), 2)
        self.assertEqual(len(history["improvement"]), 1)

    def test_132_system_not_in_graph_excluded(self):
        mock = MagicMock()
        rec = MagicMock()
        rec.target_system = "nonexistent"
        rec.completed_at = "2026-01-01"
        rec.selected_at = "2026-01-01"
        rec.predicted_score = 0.5
        rec.source = "test"
        mock.list_records.return_value = [rec]
        history = self.engine._collect_history(mock, self.graph)
        self.assertNotIn("nonexistent", history)

    def test_133_record_with_no_timestamp_skipped(self):
        mock = MagicMock()
        rec = MagicMock()
        rec.target_system = "execution"
        rec.completed_at = None
        rec.selected_at = None
        rec.predicted_score = 0.5
        rec.source = "test"
        mock.list_records.return_value = [rec]
        history = self.engine._collect_history(mock, self.graph)
        self.assertNotIn("execution", history)

    def test_134_store_exception_returns_empty(self):
        mock = MagicMock()
        mock.list_records.side_effect = Exception("DB error")
        history = self.engine._collect_history(mock, self.graph)
        self.assertEqual(history, {})


if __name__ == "__main__":
    unittest.main()
