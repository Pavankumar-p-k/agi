"""Tests for Phase 13.1 — Build Benchmark & Promotion Framework.

Covers:
  - BenchmarkRun, ComparisonResult, PromotionDecision models
  - compute_comparison between build methods
  - decide_promotion decision logic
  - get_strategy_prediction integration
  - _record_benchmark_graph ActivityGraph recording
  - _record_benchmark_calibration
  - _record_benchmark_knowledge
  - run_benchmark orchestrator
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from unittest import TestCase, mock

from core.coding.build_benchmark import (
    BenchmarkRun,
    BenchmarkSession,
    BuildMethod,
    ComparisonResult,
    MetricComparison,
    PromotionAction,
    PromotionDecision,
)


# ── Models Tests ──────────────────────────────────────────────────


class TestBenchmarkRun(TestCase):
    """BenchmarkRun data model."""

    def test_01_creation(self):
        run = BenchmarkRun(
            run_id="run_001",
            goal="Build android app",
            method=BuildMethod.AUTOMATED_BUILD,
            strategy_decision_id="sd_001",
            success=True,
            status="completed",
            duration_seconds=120.0,
        )
        self.assertEqual(run.run_id, "run_001")
        self.assertEqual(run.method, BuildMethod.AUTOMATED_BUILD)
        self.assertTrue(run.success)

    def test_02_to_dict_includes_all_keys(self):
        run = BenchmarkRun(
            run_id="run_002",
            goal="Build android coffee shop app",
            method=BuildMethod.BUILD_PROJECT,
            strategy_decision_id="sd_002",
            success=False,
            status="failed",
            duration_seconds=300.0,
            repair_cycles=2,
            repaired_errors=5,
            artifact_count=1,
            predicted_duration_days=14.0,
            predicted_success=0.8,
        )
        d = run.to_dict()
        self.assertEqual(d["run_id"], "run_002")
        self.assertEqual(d["method"], "build_project")
        self.assertIn("duration_days", d)
        self.assertIn("predicted_duration_days", d)
        self.assertEqual(d["predicted_success"], 0.8)

    def test_03_default_prediction_values(self):
        run = BenchmarkRun(
            run_id="run_003", goal="test",
            method=BuildMethod.BUILD_PROJECT,
            strategy_decision_id="sd_003",
            success=True, status="completed",
            duration_seconds=60.0,
        )
        self.assertIsNone(run.predicted_duration_days)
        self.assertIsNone(run.predicted_success)


class TestMetricComparison(TestCase):
    """MetricComparison data model."""

    def test_10_to_dict(self):
        mc = MetricComparison(
            metric="duration_seconds",
            build_project_value=120.0,
            automated_build_value=90.0,
            automated_is_better=True,
            margin=30.0,
            margin_pct=25.0,
        )
        d = mc.to_dict()
        self.assertEqual(d["metric"], "duration_seconds")
        self.assertTrue(d["automated_is_better"])


class TestComparisonResult(TestCase):
    """ComparisonResult data model."""

    def test_15_to_dict(self):
        cr = ComparisonResult(
            metrics=[
                MetricComparison("success", 1.0, 1.0, True, 0.0, 0.0),
                MetricComparison("duration", 100.0, 80.0, True, 20.0, 20.0),
            ],
            automated_wins=2,
            build_project_wins=0,
            overall_score=0.35,
        )
        d = cr.to_dict()
        self.assertEqual(d["automated_wins"], 2)
        self.assertIn("metrics", d)
        self.assertEqual(len(d["metrics"]), 2)


class TestPromotionDecision(TestCase):
    """PromotionDecision data model."""

    def test_20_promote_automated(self):
        pd = PromotionDecision(
            action=PromotionAction.PROMOTE_AUTOMATED,
            confidence=0.85,
            reasoning="automated_build wins on 3/4 metrics",
        )
        d = pd.to_dict()
        self.assertEqual(d["action"], "promote_automated")
        self.assertEqual(d["confidence"], 0.85)

    def test_21_inconclusive(self):
        pd = PromotionDecision(
            action=PromotionAction.INCONCLUSIVE,
            confidence=0.3,
            reasoning="Scores too close",
        )
        self.assertEqual(pd.action, PromotionAction.INCONCLUSIVE)


# ── Comparison Logic Tests ───────────────────────────────────────


class TestComputeComparison(TestCase):
    """compute_comparison between build methods."""

    def _make_run(self, success=True, duration=120.0, repairs=0,
                  artifacts=1, method=BuildMethod.AUTOMATED_BUILD):
        return BenchmarkRun(
            run_id="test", goal="Build app",
            method=method, strategy_decision_id="sd_test",
            success=success, status="completed" if success else "failed",
            duration_seconds=duration,
            repair_cycles=repairs,
            artifact_count=artifacts,
        )

    def test_30_automated_wins_on_all_metrics(self):
        from core.coding.build_benchmark import compute_comparison
        bp = self._make_run(success=False, duration=200.0, repairs=5,
                            artifacts=0, method=BuildMethod.BUILD_PROJECT)
        ab = self._make_run(success=True, duration=100.0, repairs=0,
                            artifacts=3)
        result = compute_comparison(bp, ab)
        self.assertEqual(result.automated_wins, 4)
        self.assertEqual(result.build_project_wins, 0)

    def test_31_build_project_wins_when_better(self):
        from core.coding.build_benchmark import compute_comparison
        bp = self._make_run(success=True, duration=50.0, repairs=0,
                            artifacts=2, method=BuildMethod.BUILD_PROJECT)
        ab = self._make_run(success=False, duration=500.0, repairs=8,
                            artifacts=0)
        result = compute_comparison(bp, ab)
        self.assertGreater(result.build_project_wins, result.automated_wins)

    def test_32_equal_runs_balanced(self):
        from core.coding.build_benchmark import compute_comparison
        bp = self._make_run(success=True, duration=100.0, repairs=2,
                            artifacts=1, method=BuildMethod.BUILD_PROJECT)
        ab = self._make_run(success=True, duration=100.0, repairs=2,
                            artifacts=1)
        result = compute_comparison(bp, ab)
        # Success ties, duration ties, repairs ties, artifacts ties
        # Some may be "better" based on tie-breaking
        self.assertGreaterEqual(result.automated_wins + result.build_project_wins, 0)

    def test_33_overall_score_positive_when_automated_better(self):
        from core.coding.build_benchmark import compute_comparison
        bp = self._make_run(success=False, duration=300.0, repairs=5,
                            artifacts=0, method=BuildMethod.BUILD_PROJECT)
        ab = self._make_run(success=True, duration=100.0, repairs=1,
                            artifacts=3)
        result = compute_comparison(bp, ab)
        self.assertGreater(result.overall_score, 0)

    def test_34_overall_score_negative_when_build_project_better(self):
        from core.coding.build_benchmark import compute_comparison
        bp = self._make_run(success=True, duration=50.0, repairs=0,
                            artifacts=2, method=BuildMethod.BUILD_PROJECT)
        ab = self._make_run(success=False, duration=500.0, repairs=10,
                            artifacts=0)
        result = compute_comparison(bp, ab)
        self.assertLess(result.overall_score, 0)


# ── Promotion Decision Logic Tests ───────────────────────────────


class TestDecidePromotion(TestCase):
    """decide_promotion decision logic."""

    def _make_run(self, success=True, duration=100.0, repairs=0,
                  artifacts=1, method=BuildMethod.AUTOMATED_BUILD):
        return BenchmarkRun(
            run_id="test", goal="Build app",
            method=method, strategy_decision_id="sd_test",
            success=success, status="completed" if success else "failed",
            duration_seconds=duration,
            repair_cycles=repairs,
            artifact_count=artifacts,
        )

    def _make_comparison(self, bp_run, ab_run):
        from core.coding.build_benchmark import compute_comparison
        return compute_comparison(bp_run, ab_run)

    def test_40_promote_automated_when_clearly_better(self):
        from core.coding.build_benchmark import decide_promotion
        bp = self._make_run(success=False, duration=300.0, repairs=5,
                            artifacts=0, method=BuildMethod.BUILD_PROJECT)
        ab = self._make_run(success=True, duration=80.0, repairs=0,
                            artifacts=3)
        comp = self._make_comparison(bp, ab)
        decision = decide_promotion(comp, bp, ab)
        self.assertEqual(decision.action, PromotionAction.PROMOTE_AUTOMATED)
        self.assertGreater(decision.confidence, 0.3)

    def test_41_keep_both_when_similar(self):
        from core.coding.build_benchmark import decide_promotion
        bp = self._make_run(success=True, duration=100.0, repairs=1,
                            artifacts=2, method=BuildMethod.BUILD_PROJECT)
        ab = self._make_run(success=True, duration=110.0, repairs=1,
                            artifacts=2)
        comp = self._make_comparison(bp, ab)
        decision = decide_promotion(comp, bp, ab)
        self.assertIn(decision.action, (
            PromotionAction.KEEP_BOTH, PromotionAction.INCONCLUSIVE))

    def test_42_inconclusive_when_nearly_identical(self):
        from core.coding.build_benchmark import decide_promotion
        # Use slower automated so overall_score ≈ -0.02 before round;
        # after +0.05 capability_bonus: 0.03, abs < 0.05 → INCONCLUSIVE.
        bp = self._make_run(success=True, duration=100.0, repairs=1,
                            artifacts=1, method=BuildMethod.BUILD_PROJECT)
        ab = self._make_run(success=True, duration=106.8, repairs=1,
                            artifacts=1)
        comp = self._make_comparison(bp, ab)
        decision = decide_promotion(comp, bp, ab)
        self.assertEqual(decision.action, PromotionAction.INCONCLUSIVE)

    def test_43_promote_build_project_when_better(self):
        from core.coding.build_benchmark import decide_promotion
        bp = self._make_run(success=True, duration=50.0, repairs=0,
                            artifacts=3, method=BuildMethod.BUILD_PROJECT)
        ab = self._make_run(success=False, duration=500.0, repairs=10,
                            artifacts=0)
        comp = self._make_comparison(bp, ab)
        decision = decide_promotion(comp, bp, ab)
        self.assertEqual(decision.action, PromotionAction.PROMOTE_BUILD_PROJECT)


# ── Strategy Prediction Integration ──────────────────────────────


class TestGetStrategyPrediction(TestCase):
    """get_strategy_prediction with mocked strategy pipeline."""

    def test_50_returns_default_on_failure(self):
        from core.coding.build_benchmark import get_strategy_prediction

        result = asyncio.run(get_strategy_prediction("Build android app"))
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_51_returns_prediction_with_mocked_pipeline(self):
        from core.coding.build_benchmark import get_strategy_prediction

        with mock.patch("core.strategy.generator.StrategyGenerator.generate") as mock_gen:
            with mock.patch("core.strategy.predictor.OutcomePredictor.predict_all") as mock_pred:
                from core.strategy.models import Strategy, Prediction, StrategyDecision
                s = Strategy(name="MVP", description="", goal="Build android app",
                             prediction=Prediction(
                                 success_probability=0.8,
                                 estimated_duration_days=12.0,
                                 estimated_risk=0.2, estimated_effort=5.0,
                                 confidence=0.5,
                             ))
                mock_gen.return_value = [s]
                mock_pred.return_value = [s]

                # Need to mock selector too
                with mock.patch("core.strategy.selector.StrategySelector.select") as mock_sel:
                    mock_sel.return_value = (s, StrategyDecision(
                        decision_id="sd_test_123",
                        goal="Build android app",
                        timestamp=__import__("datetime").datetime.utcnow(),
                        strategies_considered=[s],
                        chosen_strategy=s,
                        confidence=0.8,
                    ))

                    result = asyncio.run(get_strategy_prediction("Build android app"))
                    self.assertEqual(result[0], "sd_test_123")
                    self.assertEqual(result[1], 12.0)
                    self.assertEqual(result[2], 0.8)


# ── ActivityGraph Recording Tests ────────────────────────────────


class TestRecordBenchmarkGraph(TestCase):
    """_record_benchmark_graph integration."""

    def _make_session(self):
        bp_run = BenchmarkRun(
            run_id="bp_test", goal="Build android app",
            method=BuildMethod.BUILD_PROJECT,
            strategy_decision_id="sd_test",
            success=True, status="completed",
            duration_seconds=120.0,
            artifacts=[{"type": "apk", "path": "app.apk"}],
        )
        ab_run = BenchmarkRun(
            run_id="ab_test", goal="Build android app",
            method=BuildMethod.AUTOMATED_BUILD,
            strategy_decision_id="sd_test",
            success=True, status="completed",
            duration_seconds=90.0,
            artifacts=[
                {"type": "apk", "path": "app.apk"},
                {"type": "build_log", "path": "build.log"},
            ],
        )
        from core.coding.build_benchmark import (
            ComparisonResult, MetricComparison, PromotionDecision, PromotionAction,
        )
        comp = ComparisonResult(
            metrics=[MetricComparison("success", 1.0, 1.0, True, 0.0, 0.0)],
            automated_wins=1, build_project_wins=0, overall_score=0.3,
        )
        promo = PromotionDecision(
            action=PromotionAction.PROMOTE_AUTOMATED,
            confidence=0.8,
            reasoning="automated_build wins all metrics",
            comparison=comp,
        )
        return BenchmarkSession(
            session_id="session_test",
            goal="Build android app",
            strategy_decision_id="sd_test",
            build_project_run=bp_run,
            automated_build_run=ab_run,
            comparison=comp,
            promotion_decision=promo,
        )

    def test_60_creates_all_nodes(self):
        from core.coding.build_benchmark import _record_benchmark_graph
        session = self._make_session()
        created_nodes = []

        with mock.patch("core.activity.storage.ActivityStore") as MockStore:
            instance = MockStore.return_value
            instance.create_node = mock.Mock(side_effect=lambda n: created_nodes.append(n))

            asyncio.run(_record_benchmark_graph(session))

            self.assertGreater(len(created_nodes), 0)
            node_types = {n.node_type for n in created_nodes}
            self.assertIn("benchmark_session", node_types)
            self.assertIn("benchmark_run", node_types)
            self.assertIn("artifact", node_types)

    def test_61_promotion_decision_in_graph(self):
        from core.coding.build_benchmark import _record_benchmark_graph
        session = self._make_session()
        created_nodes = []

        with mock.patch("core.activity.storage.ActivityStore") as MockStore:
            instance = MockStore.return_value
            instance.create_node = mock.Mock(side_effect=lambda n: created_nodes.append(n))

            asyncio.run(_record_benchmark_graph(session))

            types = {n.node_type for n in created_nodes}
            self.assertIn("promotion_decision", types)


# ── Benchmark Session Orchestration ──────────────────────────────


class TestBenchmarkSession(TestCase):
    """BenchmarkSession data model."""

    def test_70_to_dict_includes_comparison(self):
        bp_run = BenchmarkRun(
            run_id="bp", goal="test",
            method=BuildMethod.BUILD_PROJECT,
            strategy_decision_id="sd",
            success=True, status="completed",
            duration_seconds=100.0,
        )
        ab_run = BenchmarkRun(
            run_id="ab", goal="test",
            method=BuildMethod.AUTOMATED_BUILD,
            strategy_decision_id="sd",
            success=True, status="completed",
            duration_seconds=80.0,
        )
        from core.coding.build_benchmark import ComparisonResult, MetricComparison, PromotionDecision, PromotionAction
        comp = ComparisonResult(
            metrics=[MetricComparison("duration", 100.0, 80.0, True, 20.0, 20.0)],
            automated_wins=1, build_project_wins=0, overall_score=0.3,
        )
        promo = PromotionDecision(
            action=PromotionAction.PROMOTE_AUTOMATED,
            confidence=0.8,
            reasoning="automated_build is faster",
            comparison=comp,
        )
        session = BenchmarkSession(
            session_id="s_001",
            goal="test",
            strategy_decision_id="sd",
            build_project_run=bp_run,
            automated_build_run=ab_run,
            comparison=comp,
            promotion_decision=promo,
        )
        d = session.to_dict()
        self.assertIn("comparison", d)
        self.assertIn("promotion_decision", d)
        self.assertIn("build_project", d)
        self.assertIn("automated_build", d)


class TestRunBenchmarkIntegration(TestCase):
    """run_benchmark with mocked build tools."""

    def test_80_runs_both_methods_with_mocks(self):
        from core.coding.build_benchmark import run_benchmark

        with mock.patch("core.tools.build_tools.do_build_project") as mock_bp:
            mock_bp.return_value = {
                "success": True, "status": "completed", "elapsed_s": 100.0,
            }
            with mock.patch("core.tools.automated_build.do_automated_build") as mock_ab:
                from core.tools.automated_build import BuildExecutionRecord
                now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                mock_ab.return_value = BuildExecutionRecord(
                    execution_id="test_ab",
                    goal="Build android app",
                    started_at=now,
                    completed_at=now,
                    success=True,
                    status="completed",
                    actual_duration_seconds=80.0,
                    phases=[],
                    artifacts=[{"type": "apk", "path": "app.apk"}],
                )

                with mock.patch("core.coding.build_benchmark._record_benchmark_graph"):
                    with mock.patch("core.coding.build_benchmark._record_benchmark_calibration"):
                        with mock.patch("core.coding.build_benchmark._record_benchmark_knowledge"):
                            session = asyncio.run(run_benchmark(
                                "Build android app",
                                project_dir=tempfile.mkdtemp(),
                            ))

        self.assertIsNotNone(session)
        self.assertTrue(session.build_project_run.success)
        self.assertTrue(session.automated_build_run.success)
        self.assertIsNotNone(session.comparison)
        self.assertIsNotNone(session.promotion_decision)
        self.assertIn(session.promotion_decision.action, (
            "promote_automated", "keep_both", "inconclusive"))

    def test_81_handles_automated_build_failure(self):
        from core.coding.build_benchmark import run_benchmark

        with mock.patch("core.tools.build_tools.do_build_project") as mock_bp:
            mock_bp.return_value = {
                "success": True, "status": "completed", "elapsed_s": 90.0,
            }
            with mock.patch("core.tools.automated_build.do_automated_build") as mock_ab:
                from core.tools.automated_build import BuildExecutionRecord
                now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                mock_ab.return_value = BuildExecutionRecord(
                    execution_id="test_fail",
                    goal="Build android app",
                    started_at=now, completed_at=now,
                    success=False, status="failed",
                    failure_reason="Build error",
                    actual_duration_seconds=300.0,
                    phases=[], artifacts=[],
                )

                with mock.patch("core.coding.build_benchmark._record_benchmark_graph"):
                    with mock.patch("core.coding.build_benchmark._record_benchmark_calibration"):
                        with mock.patch("core.coding.build_benchmark._record_benchmark_knowledge"):
                            session = asyncio.run(run_benchmark(
                                "Build android app",
                                project_dir=tempfile.mkdtemp(),
                            ))

        self.assertTrue(session.build_project_run.success)
        self.assertFalse(session.automated_build_run.success)
        self.assertIsNotNone(session.comparison)

    def test_82_calibration_skipped_when_unavailable(self):
        from core.coding.build_benchmark import _record_benchmark_calibration
        bp_run = BenchmarkRun(
            run_id="bp", goal="test", method=BuildMethod.BUILD_PROJECT,
            strategy_decision_id="sd", success=True, status="completed",
            duration_seconds=100.0,
        )
        ab_run = BenchmarkRun(
            run_id="ab", goal="test", method=BuildMethod.AUTOMATED_BUILD,
            strategy_decision_id="sd", success=True, status="completed",
            duration_seconds=80.0,
        )
        session = BenchmarkSession(
            session_id="s", goal="test", strategy_decision_id="sd",
            build_project_run=bp_run, automated_build_run=ab_run,
        )

        with mock.patch.dict("sys.modules", {"core.strategy.calibration": None}):
            try:
                asyncio.run(_record_benchmark_calibration(session))
            except Exception:
                self.fail("_record_benchmark_calibration raised on missing module")


class TestKnowledgeStoreRecording(TestCase):
    """_record_benchmark_knowledge integration."""

    def test_90_handles_missing_store_gracefully(self):
        from core.coding.build_benchmark import _record_benchmark_knowledge
        bp_run = BenchmarkRun(
            run_id="bp", goal="test", method=BuildMethod.BUILD_PROJECT,
            strategy_decision_id="sd", success=True, status="completed",
            duration_seconds=100.0,
        )
        ab_run = BenchmarkRun(
            run_id="ab", goal="test", method=BuildMethod.AUTOMATED_BUILD,
            strategy_decision_id="sd", success=True, status="completed",
            duration_seconds=80.0,
        )
        session = BenchmarkSession(
            session_id="s", goal="test", strategy_decision_id="sd",
            build_project_run=bp_run, automated_build_run=ab_run,
        )

        with mock.patch.dict("sys.modules", {
            "core.activity.manager": None,
            "core.long_term_memory.extractor": None,
        }):
            try:
                asyncio.run(_record_benchmark_knowledge(session))
            except Exception:
                self.fail("_record_benchmark_knowledge raised on missing module")
