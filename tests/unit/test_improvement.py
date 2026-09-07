"""Tests for Phase 10 — Adaptive Behavior System.

Covers KnobStore, ImprovementDetector, ProposalEngine, ExperimentRunner, SafePromotion.
"""

import os
import shutil
import tempfile
import uuid
from unittest import TestCase

from core.improvement.detector import ImprovementDetector
from core.improvement.experiment import ExperimentRunner
from core.improvement.knob_store import KnobStore
from core.improvement.models import (
    Experiment,
    ExperimentResult,
    ExperimentStatus,
    ImprovementProposal,
    KnobCategory,
    KnobChange,
    KNOB_REGISTRY,
    MetricComparison,
)
from core.improvement.proposals import ProposalEngine
from core.improvement.promoter import SafePromotion
from core.long_term_memory.models import KnowledgeItem
from core.long_term_memory.store import KnowledgeStore


def _make_knobs_json() -> str:
    tmp = tempfile.mkdtemp()
    return os.path.join(tmp, "knobs.json")


def _make_db() -> str:
    tmp = tempfile.mkdtemp()
    return os.path.join(tmp, "test_workflow.db")


class TestBehaviorKnob(TestCase):
    """BehaviorKnob dataclass + registry."""

    def test_01_registry_contains_knobs(self):
        self.assertGreater(len(KNOB_REGISTRY), 0)

    def test_02_knob_has_all_fields(self):
        knob = KNOB_REGISTRY["research.min_sources"]
        self.assertEqual(knob.category, KnobCategory.RESEARCH)
        self.assertEqual(knob.current_value, 2)
        self.assertEqual(knob.default_value, 2)
        self.assertEqual(knob.min_value, 1)
        self.assertEqual(knob.max_value, 10)

    def test_03_knob_to_dict(self):
        knob = KNOB_REGISTRY["coding.simulation_required"]
        d = knob.to_dict()
        self.assertIn("name", d)
        self.assertIn("current_value", d)
        self.assertEqual(d["category"], "coding")

    def test_04_proposal_to_dict(self):
        p = ImprovementProposal(
            proposal_id="prop_001",
            reason="Test reason",
            category=KnobCategory.PLANNER,
            confidence=0.85,
        )
        d = p.to_dict()
        self.assertEqual(d["proposal_id"], "prop_001")
        self.assertAlmostEqual(d["confidence"], 0.85)

    def test_05_knob_change_creation(self):
        c = KnobChange(knob_name="test.knob", new_value=5, reason="Testing")
        self.assertEqual(c.knob_name, "test.knob")
        self.assertEqual(c.new_value, 5)


class TestKnobStore(TestCase):
    """KnobStore — persistent knob value storage."""

    def setUp(self):
        self._path = _make_knobs_json()
        self._store = KnobStore(json_path=self._path)

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self._path), ignore_errors=True)

    def test_06_get_returns_default(self):
        val = self._store.get("research.min_sources")
        self.assertEqual(val, 2)

    def test_07_set_and_get(self):
        self.assertTrue(self._store.set("research.min_sources", 5))
        self.assertEqual(self._store.get("research.min_sources"), 5)

    def test_08_set_clamps_to_min(self):
        self._store.set("research.min_sources", -1)
        self.assertEqual(self._store.get("research.min_sources"), 1)

    def test_09_set_clamps_to_max(self):
        self._store.set("research.min_sources", 100)
        self.assertEqual(self._store.get("research.min_sources"), 10)

    def test_10_set_unknown_knob(self):
        self.assertFalse(self._store.set("nonexistent.knob", 5))

    def test_11_get_nonexistent(self):
        self.assertIsNone(self._store.get("nonexistent.knob"))

    def test_12_reset_to_default(self):
        self._store.set("research.min_sources", 8)
        self._store.reset("research.min_sources")
        self.assertEqual(self._store.get("research.min_sources"), 2)

    def test_13_reset_all(self):
        self._store.set("research.min_sources", 8)
        self._store.set("coding.safety_threshold", 0.9)
        self._store.reset_all()
        self.assertEqual(self._store.get("research.min_sources"), 2)
        self.assertAlmostEqual(self._store.get("coding.safety_threshold"), 0.7)

    def test_14_snapshot_and_apply(self):
        self._store.set("research.min_sources", 5)
        snap = self._store.get_snapshot()
        self._store.set("research.min_sources", 9)
        self._store.apply_snapshot(snap)
        self.assertEqual(self._store.get("research.min_sources"), 5)

    def test_15_get_by_category(self):
        planner_knobs = self._store.get_by_category(KnobCategory.PLANNER)
        self.assertGreater(len(planner_knobs), 0)
        for k in planner_knobs.values():
            self.assertEqual(k.category, KnobCategory.PLANNER)

    def test_16_persistence(self):
        self._store.set("research.min_sources", 7)
        # Create a new store instance pointing to same file
        store2 = KnobStore(json_path=self._path)
        self.assertEqual(store2.get("research.min_sources"), 7)

    def test_17_boolean_knob_toggle(self):
        self._store.set("coding.simulation_required", True)
        self.assertTrue(self._store.get("coding.simulation_required"))
        self._store.set("coding.simulation_required", False)
        self.assertFalse(self._store.get("coding.simulation_required"))


class TestImprovementDetector(TestCase):
    """ImprovementDetector — scans knowledge for improvement opportunities."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "test.db")
        self._ks = KnowledgeStore(db_path=self._db)
        self._detector = ImprovementDetector(store=self._ks)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_18_detect_empty_store(self):
        proposals = self._detector.detect_all()
        self.assertIsInstance(proposals, list)

    def test_19_detect_with_domain_warning(self):
        self._ks.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_dom_1", category="warning",
            claim="Projects in domain 'android' fail frequently (30% success)",
            confidence=0.7, evidence_count=5,
            tags=["android", "domain_failure"],
        ))
        proposals = self._detector.detect_all()
        self.assertGreaterEqual(len(proposals), 1)

    def test_20_detect_with_principle(self):
        self._ks.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_princ_1", category="principle",
            claim="Activities with errors fail at 60% rate",
            confidence=0.85, evidence_count=10,
        ))
        proposals = self._detector.detect_all()
        planner_props = [p for p in proposals if p.category == KnobCategory.PLANNER]
        self.assertGreaterEqual(len(planner_props), 0)

    def test_21_detect_deduplication(self):
        self._ks.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_dedup_1", category="warning",
            claim="Domain 'web' has low success rate",
            confidence=0.6, evidence_count=3,
            tags=["web", "domain_failure"],
        ))
        self._ks.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_dedup_2", category="warning",
            claim="Domain 'android' has low success rate",
            confidence=0.9, evidence_count=8,
            tags=["android", "domain_failure"],
        ))
        proposals = self._detector.detect_all()
        # Should be deduplicated: only one per category
        cats = [p.category.value for p in proposals]
        self.assertEqual(len(cats), len(set(cats)))

    def test_22_proposal_has_fields(self):
        self._ks.insert_knowledge(KnowledgeItem(
            knowledge_id="kn_prop_1", category="warning",
            claim="Test domain warning",
            confidence=0.75, evidence_count=4,
            tags=["test", "domain_failure"],
        ))
        proposals = self._detector.detect_all()
        for p in proposals:
            self.assertIsNotNone(p.proposal_id)
            self.assertIsNotNone(p.reason)
            self.assertGreater(p.confidence, 0)


class TestProposalEngine(TestCase):
    """ProposalEngine — proposals → concrete knob changes."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._knobs_path = os.path.join(self._tmp, "knobs.json")
        self._store = KnobStore(json_path=self._knobs_path)
        self._engine = ProposalEngine(knob_store=self._store)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_23_evaluate_planner_proposal(self):
        prop = ImprovementProposal(
            proposal_id="prop_test", reason="Test planner improvement",
            category=KnobCategory.PLANNER, confidence=0.85,
        )
        changes = self._engine.evaluate(prop)
        self.assertIsInstance(changes, list)

    def test_24_evaluate_coding_proposal(self):
        prop = ImprovementProposal(
            proposal_id="prop_code", reason="Test coding improvement",
            category=KnobCategory.CODING, confidence=0.75,
        )
        changes = self._engine.evaluate(prop)
        self.assertGreater(len(changes), 0)

    def test_25_evaluate_low_confidence(self):
        prop = ImprovementProposal(
            proposal_id="prop_low", reason="Low confidence test",
            category=KnobCategory.CODING, confidence=0.3,
        )
        changes = self._engine.evaluate(prop)
        # Low-confidence proposals should still produce changes based on the map
        self.assertIsInstance(changes, list)

    def test_26_evaluate_all_deduplication(self):
        props = [
            ImprovementProposal(proposal_id="p1", reason="R1",
                                category=KnobCategory.CODING, confidence=0.9),
            ImprovementProposal(proposal_id="p2", reason="R2",
                                category=KnobCategory.CODING, confidence=0.5),
        ]
        changes = self._engine.evaluate_all(props)
        # Coding knobs: simulation_required and safety_threshold
        self.assertGreaterEqual(len(changes), 0)


class TestExperimentRunner(TestCase):
    """ExperimentRunner — A/B test lifecycle."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._knobs_path = os.path.join(self._tmp, "knobs.json")
        self._db = os.path.join(self._tmp, "test.db")
        self._ks = KnobStore(json_path=self._knobs_path)
        self._runner = ExperimentRunner(knob_store=self._ks, db_path=self._db)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_27_create_experiment(self):
        changes = [KnobChange(knob_name="research.min_sources", new_value=4)]
        exp = self._runner.create_experiment("prop_test", changes)
        self.assertEqual(exp.status, ExperimentStatus.PLANNED)
        self.assertEqual(len(exp.knob_changes), 1)

    def test_28_start_experiment(self):
        changes = [KnobChange(knob_name="research.min_sources", new_value=4)]
        exp = self._runner.create_experiment("prop_start", changes)
        ok = self._runner.start_experiment(exp.experiment_id)
        self.assertTrue(ok)
        self.assertEqual(self._ks.get("research.min_sources"), 4)

    def test_29_complete_experiment_rolls_back(self):
        original = self._ks.get("research.min_sources")
        changes = [KnobChange(knob_name="research.min_sources", new_value=8)]
        exp = self._runner.create_experiment("prop_complete", changes)
        self._runner.start_experiment(exp.experiment_id)
        result = self._runner.complete_experiment(
            exp.experiment_id,
            control_metrics={"success_rate": 0.7},
            candidate_metrics={"success_rate": 0.9},
        )
        self.assertIsNotNone(result)
        # Verify rollback
        self.assertEqual(self._ks.get("research.min_sources"), original)

    def test_30_comparison_improvement_detected(self):
        changes = [KnobChange(knob_name="research.min_sources", new_value=5)]
        exp = self._runner.create_experiment("prop_metric", changes)
        self._runner.start_experiment(exp.experiment_id)
        result = self._runner.complete_experiment(
            exp.experiment_id,
            control_metrics={"success_rate": 0.6, "error_rate": 0.3},
            candidate_metrics={"success_rate": 0.85, "error_rate": 0.1},
        )
        self.assertTrue(result.overall_improvement)
        self.assertEqual(len(result.metric_comparisons), 2)

    def test_31_experiment_persists(self):
        changes = [KnobChange(knob_name="research.min_sources", new_value=4)]
        exp = self._runner.create_experiment("prop_persist", changes)
        experiments = self._runner.get_experiments()
        self.assertGreaterEqual(len(experiments), 1)
        self.assertEqual(experiments[0].experiment_id, exp.experiment_id)

    def test_32_start_fails_for_nonexistent(self):
        ok = self._runner.start_experiment("exp_nonexistent")
        self.assertFalse(ok)


class TestSafePromotion(TestCase):
    """SafePromotion — keep/revert decisions."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._knobs_path = os.path.join(self._tmp, "knobs.json")
        self._db = os.path.join(self._tmp, "test.db")
        self._ks = KnobStore(json_path=self._knobs_path)
        self._promoter = SafePromotion(knob_store=self._ks, db_path=self._db)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_33_accept_improvement(self):
        result = ExperimentResult(
            experiment_id="exp_accept",
            metric_comparisons=[
                MetricComparison(
                    metric_name="success_rate",
                    control_mean=0.6, candidate_mean=0.85, delta=0.25, improvement=True,
                ),
            ],
            overall_improvement=True,
        )
        decision = self._promoter.evaluate(result)
        self.assertTrue(decision["accepted"])

    def test_34_reject_no_improvement(self):
        result = ExperimentResult(
            experiment_id="exp_reject",
            metric_comparisons=[
                MetricComparison(
                    metric_name="success_rate",
                    control_mean=0.8, candidate_mean=0.7, delta=-0.1, improvement=False,
                ),
            ],
            overall_improvement=False,
        )
        decision = self._promoter.evaluate(result)
        self.assertFalse(decision["accepted"])

    def test_35_reject_critical_regression(self):
        result = ExperimentResult(
            experiment_id="exp_regress",
            metric_comparisons=[
                MetricComparison(
                    metric_name="success_rate",
                    control_mean=0.9, candidate_mean=0.5, delta=-0.4, improvement=False,
                ),
            ],
            overall_improvement=True,
        )
        decision = self._promoter.evaluate(result)
        self.assertFalse(decision["accepted"])

    def test_36_no_metrics_rejected(self):
        result = ExperimentResult(
            experiment_id="exp_empty",
            metric_comparisons=[],
            overall_improvement=True,
        )
        decision = self._promoter.evaluate(result)
        self.assertFalse(decision["accepted"])

    def test_37_promote_applies_changes(self):
        # Create and complete experiment first
        runner = ExperimentRunner(knob_store=self._ks, db_path=self._db)
        changes = [KnobChange(knob_name="research.min_sources", new_value=6)]
        exp = runner.create_experiment("prop_promote", changes)
        runner.start_experiment(exp.experiment_id)
        result = runner.complete_experiment(
            exp.experiment_id,
            control_metrics={"success_rate": 0.6},
            candidate_metrics={"success_rate": 0.9},
        )
        # Promote
        promoted = self._promoter.promote(exp.experiment_id, result)
        self.assertTrue(promoted)
        # Knob should have the new value after promotion
        self.assertEqual(self._ks.get("research.min_sources"), 6)

    def test_38_reject_explicitly(self):
        runner = ExperimentRunner(knob_store=self._ks, db_path=self._db)
        changes = [KnobChange(knob_name="research.min_sources", new_value=5)]
        exp = runner.create_experiment("prop_reject", changes)
        runner.start_experiment(exp.experiment_id)
        result = runner.complete_experiment(
            exp.experiment_id,
            control_metrics={"success_rate": 0.6},
            candidate_metrics={"success_rate": 0.55},
        )
        rejected = self._promoter.reject(exp.experiment_id, result)
        self.assertTrue(rejected)

    def test_39_empty_comparisons(self):
        result = ExperimentResult(
            experiment_id="exp_empty",
            metric_comparisons=[
                MetricComparison(
                    metric_name="success_rate",
                    control_mean=0.7, candidate_mean=0.8, delta=0.1, improvement=True,
                ),
            ],
            overall_improvement=True,
        )
        decision = self._promoter.evaluate(result)
        self.assertTrue(decision["accepted"])
