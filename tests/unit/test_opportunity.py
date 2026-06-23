"""Opportunity Discovery Engine tests — Phase 17.0 + Phase 17.1.

Phase 17.0 covers:
  - Models: Opportunity creation, to_dict, short_summary
  - Ceiling Analysis: system scores, headroom computation
  - Bottleneck Discovery: activity history → tool failure rates
  - Experiment History: experiment patterns → extension opportunities
  - Principle-Driven Discovery: principles + registry → system gaps
  - Orchestration: discover_all deduplication, ranking
  - Edge cases: empty stores, missing stores, degenerate inputs

Phase 17.1 covers:
  - OpportunityStore: CRUD, persistence, listing
  - OpportunityCalibrator: recording outcomes, metrics, adjustment factor
  - Integration: calibrator wired into engine via _apply_calibration
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from typing import Any

from core.opportunity.calibration import OpportunityCalibrator
from core.opportunity.engine import (
    OpportunityDiscoveryEngine,
    DEFAULT_SYSTEM_SCORES,
)
from core.opportunity.models import (
    Opportunity,
    OpportunitySource,
    OpportunityStatus,
)
from core.opportunity.store import OpportunityRecord, OpportunityStore


# ── Mock helpers ────────────────────────────────────────────────────────


class _MockNode:
    """Minimal ActivityNode mock with fields accessed by the engine."""

    def __init__(self, label: str, status: str):
        self.label = label
        self.status = status


class _MockActivityStore:
    """Simulates ActivityStore.get_nodes_by_type()."""

    def __init__(self, nodes: list[_MockNode] | None = None):
        self._nodes = nodes or []

    def get_nodes_by_type(self, node_type: str) -> list[_MockNode]:
        return self._nodes


class _MockKnobChange:
    def __init__(self, knob_name: str):
        self.knob_name = knob_name


class _MockExperiment:
    """Simulates an Experiment dataclass."""

    def __init__(
        self,
        experiment_id: str,
        knob_changes: list[_MockKnobChange],
        status: str = "completed",
        control_metrics: dict[str, float] | None = None,
        candidate_metrics: dict[str, float] | None = None,
    ):
        self.experiment_id = experiment_id
        self.knob_changes = knob_changes
        self.status = status
        self.control_metrics = control_metrics or {}
        self.candidate_metrics = candidate_metrics or {}


class _MockExperimentRunner:
    """Simulates ExperimentRunner.get_experiments()."""

    def __init__(self, experiments: list[_MockExperiment] | None = None):
        self._experiments = experiments or []

    def get_experiments(self, limit: int = 20) -> list[_MockExperiment]:
        return self._experiments


class _MockPrinciple:
    def __init__(
        self,
        principle_id: str,
        property_name: str,
        discrimination: float = 0.3,
        confidence: float = 0.8,
        category: str = "execution_model",
        domains: list[str] | None = None,
        status: str = "accepted",
    ):
        self.principle_id = principle_id
        self.property_name = property_name
        self.discrimination = discrimination
        self.confidence = confidence
        self.category = category
        self.domains = domains or ["build"]
        self.status = status


class _MockPrincipleStore:
    def __init__(self, principles: list[_MockPrinciple] | None = None):
        self._principles = principles or []

    def list_principles(self, status: str | None = None) -> list[_MockPrinciple]:
        if status:
            return [p for p in self._principles if p.status == status]
        return self._principles


class _MockProfile:
    def __init__(self, system_id: str, properties: dict[str, Any] | None = None):
        self.system_id = system_id
        self.properties = properties or {}


class _MockRegistry:
    def __init__(self, profiles: list[_MockProfile] | None = None):
        self._profiles = profiles or []

    def list_profiles(self) -> list[_MockProfile]:
        return self._profiles


# ── Model Tests ────────────────────────────────────────────────────────


class TestOpportunityModels(unittest.TestCase):
    """Opportunity dataclass basics."""

    def test_01_minimal_creation(self):
        opp = Opportunity(
            id="opp_01",
            target_system="test_system",
            improvement_description="Test improvement",
            source=OpportunitySource.CEILING,
            bottleneck_impact=0.5,
            improvement_headroom=0.5,
            success_probability=0.5,
            confidence=0.5,
            opportunity_score=0.0625,
            rationale="Test rationale",
        )
        self.assertEqual(opp.id, "opp_01")
        self.assertEqual(opp.target_system, "test_system")
        self.assertEqual(opp.source, OpportunitySource.CEILING)
        self.assertEqual(opp.status, OpportunityStatus.OPEN)

    def test_02_full_creation(self):
        now = datetime.now(timezone.utc)
        opp = Opportunity(
            id="opp_02",
            target_system="browser_automation",
            improvement_description="Add retry loop",
            source=OpportunitySource.BOTTLENECK,
            bottleneck_impact=0.8,
            improvement_headroom=0.6,
            success_probability=0.7,
            confidence=0.85,
            opportunity_score=0.8 * 0.6 * 0.7 * 0.85,
            rationale="Browser fails often",
            evidence=["evidence_1", "evidence_2"],
            status=OpportunityStatus.IN_PROGRESS,
            created_at=now,
        )
        self.assertEqual(opp.status, OpportunityStatus.IN_PROGRESS)
        self.assertEqual(len(opp.evidence), 2)

    def test_03_to_dict(self):
        opp = Opportunity(
            id="opp_03",
            target_system="test",
            improvement_description="desc",
            source=OpportunitySource.PRINCIPLE,
            bottleneck_impact=0.4,
            improvement_headroom=0.3,
            success_probability=0.9,
            confidence=0.8,
            opportunity_score=0.0864,
            rationale="test",
            evidence=["e1"],
        )
        d = opp.to_dict()
        self.assertEqual(d["id"], "opp_03")
        self.assertEqual(d["source"], "principle")
        self.assertEqual(d["opportunity_score"], 0.086)
        self.assertIn("target_system", d)
        self.assertIn("rationale", d)

    def test_04_short_summary(self):
        opp = Opportunity(
            id="opp_04",
            target_system="belt_quality",
            improvement_description="Add consensus scoring to belief quality",
            source=OpportunitySource.CEILING,
            bottleneck_impact=0.3,
            improvement_headroom=0.7,
            success_probability=0.6,
            confidence=0.5,
            opportunity_score=0.063,
            rationale="test",
        )
        summary = opp.short_summary()
        self.assertIn("0.06", summary)
        self.assertIn("belt_quality", summary)

    def test_05_enum_values(self):
        self.assertEqual(OpportunitySource.BOTTLENECK.value, "bottleneck")
        self.assertEqual(OpportunitySource.CEILING.value, "ceiling")
        self.assertEqual(OpportunitySource.EXPERIMENT.value, "experiment")
        self.assertEqual(OpportunitySource.PRINCIPLE.value, "principle")
        self.assertEqual(OpportunityStatus.OPEN.value, "open")
        self.assertEqual(OpportunityStatus.IN_PROGRESS.value, "in_progress")
        self.assertEqual(OpportunityStatus.COMPLETED.value, "completed")
        self.assertEqual(OpportunityStatus.REJECTED.value, "rejected")

    def test_06_default_system_scores_present(self):
        self.assertIn("self_modification", DEFAULT_SYSTEM_SCORES)
        self.assertIn("opportunity_discovery", DEFAULT_SYSTEM_SCORES)
        self.assertIn("belief_quality", DEFAULT_SYSTEM_SCORES)
        self.assertGreaterEqual(DEFAULT_SYSTEM_SCORES["opportunity_discovery"], 0.30)
        self.assertLessEqual(DEFAULT_SYSTEM_SCORES["belief_quality"], 0.95)


# ── Ceiling Discovery Tests ──────────────────────────────────────────────


class TestCeilingDiscovery(unittest.TestCase):
    """Ceiling analysis — always available, no dependencies."""

    def setUp(self):
        self.engine = OpportunityDiscoveryEngine()

    def test_10_discovers_all_systems(self):
        opportunities = self.engine.discover_ceilings()
        self.assertGreater(len(opportunities), 5)

    def test_11_low_score_systems_have_higher_score(self):
        opportunities = self.engine.discover_ceilings()
        scores = {o.target_system: o.opportunity_score for o in opportunities}
        # self_modification (0.45) should score higher than belief_quality (0.91)
        self.assertGreater(
            scores.get("self_modification", 0),
            scores.get("belief_quality", 1),
        )

    def test_12_high_score_systems_have_low_headroom(self):
        opportunities = self.engine.discover_ceilings()
        for opp in opportunities:
            if opp.target_system == "execution_infrastructure":
                self.assertLess(opp.improvement_headroom, 0.06)
                return
        self.fail("execution_infrastructure not found")

    def test_13_opportunity_score_is_product_of_four_dimensions(self):
        opportunities = self.engine.discover_ceilings()
        for opp in opportunities:
            expected = opp.bottleneck_impact * opp.improvement_headroom * opp.success_probability * opp.confidence
            self.assertAlmostEqual(opp.opportunity_score, expected, places=3)

    def test_14_excludes_negligible_headroom(self):
        engine = OpportunityDiscoveryEngine(system_scores={"perfect": 0.99})
        opportunities = engine.discover_ceilings()
        for opp in opportunities:
            if opp.target_system == "perfect":
                self.fail("Should not generate opportunity for 0.99 score")
        # Should still include other default systems
        self.assertGreater(len(opportunities), 0)

    def test_15_custom_system_scores(self):
        engine = OpportunityDiscoveryEngine(system_scores={"my_system": 0.30})
        opps = engine.discover_ceilings()
        found = [o for o in opps if o.target_system == "my_system"]
        self.assertEqual(len(found), 1)
        self.assertGreater(found[0].improvement_headroom, 0.6)

    def test_16_returns_opportunity_objects(self):
        opps = self.engine.discover_ceilings()
        for opp in opps:
            self.assertIsInstance(opp, Opportunity)
            self.assertEqual(opp.source, OpportunitySource.CEILING)

    def test_17_evidence_includes_score_info(self):
        opps = self.engine.discover_ceilings()
        for opp in opps:
            self.assertGreater(len(opp.evidence), 0)
            self.assertIn("Current score", opp.evidence[0])


# ── Bottleneck Discovery Tests ──────────────────────────────────────────


class TestBottleneckDiscovery(unittest.TestCase):
    """Bottleneck analysis — requires activity_store."""

    def setUp(self):
        self.engine = OpportunityDiscoveryEngine()

    def test_20_skip_when_no_store(self):
        opps = self.engine.discover_bottlenecks()
        self.assertEqual(opps, [])

    def test_21_skip_when_empty_store(self):
        store = _MockActivityStore(nodes=[])
        opps = self.engine.discover_bottlenecks(activity_store=store)
        self.assertEqual(opps, [])

    def test_22_detects_failing_tool(self):
        nodes = [
            _MockNode(label="browser_navigate", status="COMPLETED"),
            _MockNode(label="browser_navigate", status="FAILED"),
            _MockNode(label="browser_navigate", status="FAILED"),
            _MockNode(label="browser_navigate", status="FAILED"),
        ]
        store = _MockActivityStore(nodes=nodes)
        opps = self.engine.discover_bottlenecks(activity_store=store)
        self.assertGreater(len(opps), 0)
        browser_opps = [o for o in opps if "browser" in o.target_system]
        self.assertGreater(len(browser_opps), 0)
        self.assertGreater(browser_opps[0].bottleneck_impact, 0.3)

    def test_23_low_usage_filtered_out(self):
        nodes = [_MockNode(label="rare_tool", status="FAILED")]
        store = _MockActivityStore(nodes=nodes)
        opps = self.engine.discover_bottlenecks(activity_store=store)
        rare = [o for o in opps if "rare_tool" in o.target_system]
        self.assertEqual(len(rare), 0)

    def test_24_perfect_tool_has_low_impact(self):
        nodes = [
            _MockNode(label="reliable_tool", status="COMPLETED"),
            _MockNode(label="reliable_tool", status="COMPLETED"),
            _MockNode(label="reliable_tool", status="COMPLETED"),
            _MockNode(label="reliable_tool", status="COMPLETED"),
        ]
        store = _MockActivityStore(nodes=nodes)
        opps = self.engine.discover_bottlenecks(activity_store=store)
        reliable = [o for o in opps if "reliable_tool" in o.target_system]
        self.assertEqual(len(reliable), 0)

    def test_25_mixed_usage_ranks_by_impact(self):
        nodes = (
            [_MockNode(label="failing_often", status="FAILED") for _ in range(8)]
            + [_MockNode(label="failing_often", status="COMPLETED") for _ in range(2)]
            + [_MockNode(label="sometimes_fails", status="COMPLETED") for _ in range(8)]
            + [_MockNode(label="sometimes_fails", status="FAILED") for _ in range(2)]
        )
        store = _MockActivityStore(nodes=nodes)
        opps = self.engine.discover_bottlenecks(activity_store=store)
        failing = [o for o in opps if "failing_often" in o.target_system]
        sometimes = [o for o in opps if "sometimes_fails" in o.target_system]
        if failing and sometimes:
            self.assertGreater(failing[0].opportunity_score, sometimes[0].opportunity_score)

    def test_26_source_is_bottleneck(self):
        nodes = [
            _MockNode(label="browser_navigate", status="FAILED"),
            _MockNode(label="browser_navigate", status="FAILED"),
            _MockNode(label="browser_navigate", status="FAILED"),
            _MockNode(label="browser_navigate", status="COMPLETED"),
        ]
        store = _MockActivityStore(nodes=nodes)
        opps = self.engine.discover_bottlenecks(activity_store=store)
        self.assertEqual(opps[0].source, OpportunitySource.BOTTLENECK)

    def test_27_store_error_returns_empty(self):
        class _BrokenStore:
            def get_nodes_by_type(self, node_type):
                raise RuntimeError("Store unavailable")

        opps = self.engine.discover_bottlenecks(activity_store=_BrokenStore())
        self.assertEqual(opps, [])


# ── Experiment Discovery Tests ──────────────────────────────────────────


class TestExperimentDiscovery(unittest.TestCase):
    """Experiment pattern discovery — requires experiment_runner."""

    def setUp(self):
        self.engine = OpportunityDiscoveryEngine()

    def test_30_skip_when_no_runner(self):
        opps = self.engine.discover_from_experiments()
        self.assertEqual(opps, [])

    def test_31_skip_when_empty(self):
        runner = _MockExperimentRunner(experiments=[])
        opps = self.engine.discover_from_experiments(experiment_runner=runner)
        self.assertEqual(opps, [])

    def test_32_detects_successful_pattern(self):
        experiments = [
            _MockExperiment(
                experiment_id="exp_1",
                knob_changes=[_MockKnobChange("research.min_sources")],
                status="completed",
                control_metrics={"accuracy": 0.5},
                candidate_metrics={"accuracy": 0.8},
            ),
            _MockExperiment(
                experiment_id="exp_2",
                knob_changes=[_MockKnobChange("research.min_sources")],
                status="completed",
                control_metrics={"accuracy": 0.5},
                candidate_metrics={"accuracy": 0.9},
            ),
        ]
        runner = _MockExperimentRunner(experiments=experiments)
        opps = self.engine.discover_from_experiments(experiment_runner=runner)
        self.assertGreater(len(opps), 0)
        self.assertEqual(opps[0].source, OpportunitySource.EXPERIMENT)

    def test_33_low_success_rate_skipped(self):
        experiments = [
            _MockExperiment(
                experiment_id="exp_3",
                knob_changes=[_MockKnobChange("coding.safety_threshold")],
                status="completed",
                control_metrics={"accuracy": 0.8},
                candidate_metrics={"accuracy": 0.4},
            ),
        ]
        runner = _MockExperimentRunner(experiments=experiments)
        opps = self.engine.discover_from_experiments(experiment_runner=runner)
        self.assertEqual(opps, [])

    def test_34_multiple_experiments_aggregate(self):
        experiments = [
            _MockExperiment(
                experiment_id=f"exp_{i}",
                knob_changes=[_MockKnobChange("planner.inject_domain_patterns")],
                status="completed",
                control_metrics={"success": 0.5},
                candidate_metrics={"success": 0.7 + i * 0.05},
            )
            for i in range(5)
        ]
        runner = _MockExperimentRunner(experiments=experiments)
        opps = self.engine.discover_from_experiments(experiment_runner=runner)
        self.assertGreater(len(opps), 0)
        self.assertGreater(opps[0].confidence, 0.5)

    def test_35_runner_error_returns_empty(self):
        class _BrokenRunner:
            def get_experiments(self, limit=20):
                raise RuntimeError("No DB")

        opps = self.engine.discover_from_experiments(experiment_runner=_BrokenRunner())
        self.assertEqual(opps, [])


# ── Principle-Driven Discovery Tests ────────────────────────────────────


class TestPrincipleDiscovery(unittest.TestCase):
    """Principle-driven discovery — requires principle_store + registry."""

    def setUp(self):
        self.engine = OpportunityDiscoveryEngine()

    def test_40_skip_when_missing_store(self):
        opps = self.engine.discover_from_principles(
            principle_store=None, registry=_MockRegistry()
        )
        self.assertEqual(opps, [])

    def test_41_skip_when_missing_registry(self):
        opps = self.engine.discover_from_principles(
            principle_store=_MockPrincipleStore(), registry=None
        )
        self.assertEqual(opps, [])

    def test_42_skip_when_no_principles(self):
        store = _MockPrincipleStore(principles=[])
        registry = _MockRegistry(profiles=[_MockProfile("system_a")])
        opps = self.engine.discover_from_principles(
            principle_store=store, registry=registry
        )
        self.assertEqual(opps, [])

    def test_43_detects_missing_property(self):
        principles = [
            _MockPrinciple(
                principle_id="p_1",
                property_name="repair_capable",
                discrimination=0.31,
                confidence=0.89,
            )
        ]
        profiles = [
            _MockProfile("browser_tool", {"repair_capable": False}),
        ]
        store = _MockPrincipleStore(principles=principles)
        registry = _MockRegistry(profiles=profiles)
        opps = self.engine.discover_from_principles(
            principle_store=store, registry=registry
        )
        self.assertGreater(len(opps), 0)
        self.assertEqual(opps[0].source, OpportunitySource.PRINCIPLE)
        self.assertIn("repair_capable", opps[0].improvement_description)

    def test_44_skips_systems_with_property_already_true(self):
        principles = [
            _MockPrinciple(
                principle_id="p_1",
                property_name="repair_capable",
                discrimination=0.31,
                confidence=0.89,
            )
        ]
        profiles = [
            _MockProfile("already_fixed", {"repair_capable": True}),
        ]
        store = _MockPrincipleStore(principles=principles)
        registry = _MockRegistry(profiles=profiles)
        opps = self.engine.discover_from_principles(
            principle_store=store, registry=registry
        )
        fixed = [o for o in opps if "already_fixed" in o.target_system]
        self.assertEqual(len(fixed), 0)

    def test_45_non_accepted_principles_ignored(self):
        principles = [
            _MockPrinciple(
                principle_id="p_rejected",
                property_name="retry_capable",
                discrimination=0.2,
                confidence=0.5,
                status="rejected",
            )
        ]
        profiles = [_MockProfile("test_sys", {"retry_capable": False})]
        store = _MockPrincipleStore(principles=principles)
        registry = _MockRegistry(profiles=profiles)
        opps = self.engine.discover_from_principles(
            principle_store=store, registry=registry
        )
        self.assertEqual(opps, [])

    def test_46_principle_score_uses_discrimination(self):
        principles = [
            _MockPrinciple(
                principle_id="p_high",
                property_name="verification_builtin",
                discrimination=0.45,
                confidence=0.95,
            ),
        ]
        profiles = [
            _MockProfile("target_sys", {"verification_builtin": False}),
        ]
        store = _MockPrincipleStore(principles=principles)
        registry = _MockRegistry(profiles=profiles)
        opps = self.engine.discover_from_principles(
            principle_store=store, registry=registry
        )
        self.assertGreater(len(opps), 0)
        self.assertGreater(opps[0].bottleneck_impact, 0.5)

    def test_47_store_error_returns_empty(self):
        class _BrokenStore:
            def list_principles(self, status=None):
                raise RuntimeError("DB broken")

        opps = self.engine.discover_from_principles(
            principle_store=_BrokenStore(),
            registry=_MockRegistry(profiles=[_MockProfile("x")]),
        )
        self.assertEqual(opps, [])


# ── Orchestration Tests ─────────────────────────────────────────────────


class TestOrchestration(unittest.TestCase):
    """discover_all ranking and deduplication."""

    def setUp(self):
        self.engine = OpportunityDiscoveryEngine()

    def test_50_empty_discovery_returns_ceiling_only(self):
        """With no stores, only ceiling analysis produces results."""
        opps = self.engine.discover_all()
        self.assertGreater(len(opps), 5)
        for opp in opps:
            self.assertEqual(opp.source, OpportunitySource.CEILING)

    def test_51_includes_all_sources_when_available(self):
        nodes = [
            _MockNode(label="build_project", status="FAILED"),
            _MockNode(label="build_project", status="FAILED"),
            _MockNode(label="build_project", status="FAILED"),
            _MockNode(label="build_project", status="COMPLETED"),
        ]
        store = _MockActivityStore(nodes=nodes)

        experiments = [
            _MockExperiment(
                experiment_id="exp_a",
                knob_changes=[_MockKnobChange("research.min_sources")],
                status="completed",
                control_metrics={"acc": 0.4},
                candidate_metrics={"acc": 0.85},
            ),
        ]
        runner = _MockExperimentRunner(experiments=experiments)

        principles = [
            _MockPrinciple("p_1", "retry_capable", discrimination=0.35, confidence=0.85),
        ]
        profiles = [
            _MockProfile("some_tool", {"retry_capable": False}),
        ]
        p_store = _MockPrincipleStore(principles=principles)
        registry = _MockRegistry(profiles=profiles)

        opps = self.engine.discover_all(
            activity_store=store,
            principle_store=p_store,
            registry=registry,
            experiment_runner=runner,
        )
        sources = {o.source for o in opps}
        self.assertIn(OpportunitySource.CEILING, sources)
        self.assertIn(OpportunitySource.PRINCIPLE, sources)
        self.assertIn(OpportunitySource.EXPERIMENT, sources)
        self.assertIn(OpportunitySource.BOTTLENECK, sources)

    def test_52_results_ranked_by_score_descending(self):
        opps = self.engine.discover_all()
        for i in range(len(opps) - 1):
            self.assertGreaterEqual(opps[i].opportunity_score, opps[i + 1].opportunity_score)

    def test_53_deduplicates_same_system_source(self):
        class _DupStore:
            def get_nodes_by_type(self, node_type):
                return [
                    _MockNode(label="build_project", status="FAILED"),
                    _MockNode(label="build_project", status="FAILED"),
                    _MockNode(label="build_project", status="FAILED"),
                    _MockNode(label="build_project", status="COMPLETED"),
                ]

        opps = self.engine.discover_all(activity_store=_DupStore())
        # Only one bottleneck + all ceilings
        build_bottlenecks = [o for o in opps if o.source == OpportunitySource.BOTTLENECK and "build" in o.target_system]
        self.assertLessEqual(len(build_bottlenecks), 1)

    def test_54_custom_scores_override_defaults(self):
        engine = OpportunityDiscoveryEngine(system_scores={"belief_quality": 0.50})
        opps = engine.discover_all()
        for opp in opps:
            if opp.target_system == "belief_quality":
                # Lower score → higher headroom → higher opportunity score
                # than the default 0.91 would give
                self.assertGreater(opp.improvement_headroom, 0.4)
                return
        self.fail("belief_quality not found")


# ── Edge Cases ──────────────────────────────────────────────────────────


class TestEdgeCases(unittest.TestCase):
    """Degenerate inputs, error handling."""

    def setUp(self):
        self.engine = OpportunityDiscoveryEngine()

    def test_60_get_scored_systems(self):
        scores = self.engine.get_scored_systems()
        self.assertIsInstance(scores, dict)
        self.assertIn("opportunity_discovery", scores)

    def test_61_opportunity_with_no_evidence(self):
        opp = Opportunity(
            id="opp_no_ev",
            target_system="t",
            improvement_description="d",
            source=OpportunitySource.CEILING,
            bottleneck_impact=0.5,
            improvement_headroom=0.5,
            success_probability=0.5,
            confidence=0.5,
            opportunity_score=0.0625,
            rationale="r",
        )
        self.assertEqual(opp.evidence, [])

    def test_62_opportunity_to_dict_has_all_keys(self):
        opp = Opportunity(
            id="opp_keys",
            target_system="t",
            improvement_description="d",
            source=OpportunitySource.CEILING,
            bottleneck_impact=0.5,
            improvement_headroom=0.5,
            success_probability=0.5,
            confidence=0.5,
            opportunity_score=0.0625,
            rationale="r",
            evidence=["e1"],
            created_at=datetime.now(timezone.utc),
        )
        d = opp.to_dict()
        required_keys = {
            "id", "target_system", "improvement_description", "source",
            "bottleneck_impact", "improvement_headroom", "success_probability",
            "confidence", "calibration_accuracy", "opportunity_score",
            "rationale", "evidence", "status", "created_at",
        }
        self.assertEqual(set(d.keys()), required_keys)

    def test_63_missing_all_stores_returns_ceilings_only(self):
        opps = self.engine.discover_all(
            activity_store=None,
            principle_store=None,
            registry=None,
            experiment_runner=None,
        )
        self.assertGreater(len(opps), 0)
        for opp in opps:
            self.assertEqual(opp.source, OpportunitySource.CEILING)

    def test_64_principle_without_property_name_skipped(self):
        p_store = _MockPrincipleStore(principles=[
            _MockPrinciple("p_empty", property_name="", discrimination=0.2, confidence=0.7),
        ])
        registry = _MockRegistry(profiles=[_MockProfile("sys", {"x": False})])
        opps = self.engine.discover_from_principles(
            principle_store=p_store, registry=registry
        )
        self.assertEqual(opps, [])

    def test_65_score_formula_correct(self):
        """Verify the product formula produces expected values."""
        opp = Opportunity(
            id="check",
            target_system="t",
            improvement_description="d",
            source=OpportunitySource.CEILING,
            bottleneck_impact=0.8,
            improvement_headroom=0.6,
            success_probability=0.7,
            confidence=0.9,
            opportunity_score=0.8 * 0.6 * 0.7 * 0.9,
            rationale="r",
        )
        self.assertAlmostEqual(opp.opportunity_score, 0.3024, places=4)


# ── Phase 17.1 — OpportunityStore Tests ───────────────────────────────


class TestOpportunityStore(unittest.TestCase):
    """OpportunityRecord + OpportunityStore lifecycle."""

    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.store = OpportunityStore(db_path=self.tmp)

    def tearDown(self):
        self.store.clear()
        os.remove(self.tmp)

    def test_100_save_and_get(self):
        rec = OpportunityRecord(
            opportunity_id="opp_001",
            source="bottleneck",
            target_system="browser_automation",
            predicted_score=0.75,
            actual_improvement=0.30,
            actual_success=True,
        )
        self.store.save(rec)
        loaded = self.store.get("opp_001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.opportunity_id, "opp_001")
        self.assertEqual(loaded.source, "bottleneck")
        self.assertAlmostEqual(loaded.prediction_error, 0.45, places=3)

    def test_101_get_missing(self):
        self.assertIsNone(self.store.get("nonexistent"))

    def test_102_save_updates_existing(self):
        rec = OpportunityRecord("x", "ceiling", "s1", 0.8, 0.7, True)
        self.store.save(rec)
        updated = OpportunityRecord("x", "ceiling", "s1", 0.8, 0.9, True)
        self.store.save(updated)
        loaded = self.store.get("x")
        self.assertAlmostEqual(loaded.actual_improvement, 0.9)

    def test_103_list_records_all(self):
        for i in range(5):
            self.store.save(OpportunityRecord(
                f"opp_{i}", "bottleneck", "sys", 0.5, 0.3, i % 2 == 0
            ))
        records = self.store.list_records(limit=100)
        self.assertEqual(len(records), 5)

    def test_104_list_records_filter_by_source(self):
        for i in range(3):
            self.store.save(OpportunityRecord(f"a_{i}", "bottleneck", "sys", 0.5, 0.3, True))
            self.store.save(OpportunityRecord(f"b_{i}", "ceiling", "sys", 0.5, 0.3, True))
        records = self.store.list_records(source="bottleneck", limit=100)
        self.assertEqual(len(records), 3)
        self.assertTrue(all(r.source == "bottleneck" for r in records))

    def test_105_list_records_filter_by_target(self):
        self.store.save(OpportunityRecord("x", "b", "sys_a", 0.5, 0.3, True))
        self.store.save(OpportunityRecord("y", "b", "sys_b", 0.5, 0.3, True))
        records = self.store.list_records(target_system="sys_a", limit=100)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].target_system, "sys_a")

    def test_106_delete(self):
        rec = OpportunityRecord("del", "b", "s", 0.5, 0.3, True)
        self.store.save(rec)
        self.assertTrue(self.store.delete("del"))
        self.assertIsNone(self.store.get("del"))
        self.assertFalse(self.store.delete("del"))

    def test_107_count(self):
        self.assertEqual(self.store.count(), 0)
        self.store.save(OpportunityRecord("c1", "b", "s", 0.5, 0.3, True))
        self.store.save(OpportunityRecord("c2", "b", "s", 0.5, 0.3, True))
        self.assertEqual(self.store.count(), 2)

    def test_108_clear(self):
        self.store.save(OpportunityRecord("k", "b", "s", 0.5, 0.3, True))
        self.store.clear()
        self.assertEqual(self.store.count(), 0)

    def test_109_prediction_error_auto_computed(self):
        rec = OpportunityRecord("e", "b", "s", 0.8, 0.3, True)
        self.assertAlmostEqual(rec.prediction_error, 0.5, places=3)
        rec2 = OpportunityRecord("e2", "b", "s", 0.3, 0.8, True)
        self.assertAlmostEqual(rec2.prediction_error, -0.5, places=3)

    def test_110_roundtrip_preserves_all_fields(self):
        rec = OpportunityRecord(
            opportunity_id="rt",
            source="experiment",
            target_system="coding_intelligence",
            predicted_score=0.65,
            actual_improvement=0.55,
            actual_success=True,
            selected_at="2025-01-01T00:00:00",
            completed_at="2025-01-02T00:00:00",
        )
        self.store.save(rec)
        loaded = self.store.get("rt")
        self.assertEqual(loaded.opportunity_id, "rt")
        self.assertEqual(loaded.source, "experiment")
        self.assertEqual(loaded.target_system, "coding_intelligence")
        self.assertAlmostEqual(loaded.predicted_score, 0.65)
        self.assertAlmostEqual(loaded.actual_improvement, 0.55)
        self.assertTrue(loaded.actual_success)

    def test_111_to_dict(self):
        rec = OpportunityRecord("d", "b", "s", 0.7, 0.4, True)
        d = rec.to_dict()
        self.assertIn("opportunity_id", d)
        self.assertIn("predicted_score", d)
        self.assertIn("actual_improvement", d)
        self.assertIn("prediction_error", d)
        self.assertAlmostEqual(d["prediction_error"], 0.3, places=3)


# ── Phase 17.1 — OpportunityCalibrator Tests ──────────────────────────


class TestOpportunityCalibrator(unittest.TestCase):
    """Calibrator — recording outcomes, metrics, adjustment factors."""

    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.store = OpportunityStore(db_path=self.tmp)
        self.cal = OpportunityCalibrator(store=self.store)

    def tearDown(self):
        self.store.clear()
        os.remove(self.tmp)

    # ── Recording ─────────────────────────────────────────────────────

    def test_120_record_outcome_creates_record(self):
        rec = self.cal.record_outcome(
            opportunity_id="o1",
            source="bottleneck",
            target_system="sys_x",
            predicted_score=0.8,
            actual_improvement=0.6,
            actual_success=True,
        )
        self.assertIsNotNone(rec)
        self.assertEqual(self.store.count(), 1)

    def test_121_record_outcome_from_result(self):
        result = {"overall_improvement": True, "improvement_score": 0.75}
        rec = self.cal.record_outcome_from_result(
            opportunity_id="o2",
            source="ceiling",
            target_system="sys_y",
            predicted_score=0.5,
            result=result,
        )
        self.assertTrue(rec.actual_success)
        self.assertAlmostEqual(rec.actual_improvement, 0.75)

    def test_122_record_outcome_from_result_defaults(self):
        rec = self.cal.record_outcome_from_result(
            opportunity_id="o3", source="b", target_system="s", predicted_score=0.5
        )
        self.assertFalse(rec.actual_success)
        self.assertAlmostEqual(rec.actual_improvement, 0.0)

    # ── Metrics ───────────────────────────────────────────────────────

    def test_130_get_metrics_empty(self):
        m = self.cal.get_metrics()
        self.assertEqual(m["count"], 0)
        self.assertEqual(m["source_accuracy"], 1.0)

    def test_131_get_metrics_single_record(self):
        self.cal.record_outcome("o1", "bottleneck", "sys", 0.8, 0.6, True)
        m = self.cal.get_metrics()
        self.assertEqual(m["count"], 1)
        self.assertAlmostEqual(m["mean_error"], 0.2, places=3)

    def test_132_get_metrics_multiple(self):
        for i in range(5):
            self.cal.record_outcome(f"o{i}", "bottleneck", "sys", 0.5, 0.5, True)
        m = self.cal.get_metrics()
        self.assertEqual(m["count"], 5)
        self.assertAlmostEqual(m["mean_error"], 0.0, places=3)
        self.assertAlmostEqual(m["source_accuracy"], 1.0, places=3)

    def test_133_get_metrics_filter_source(self):
        self.cal.record_outcome("x", "bottleneck", "s", 0.8, 0.6, True)
        self.cal.record_outcome("y", "ceiling", "s", 0.5, 0.5, True)
        m = self.cal.get_metrics(source="bottleneck")
        self.assertEqual(m["count"], 1)
        self.assertAlmostEqual(m["mean_error"], 0.2, places=3)

    def test_134_get_metrics_filter_target(self):
        self.cal.record_outcome("x", "b", "sys_a", 0.8, 0.6, True)
        self.cal.record_outcome("y", "b", "sys_b", 0.5, 0.5, True)
        m = self.cal.get_metrics(target_system="sys_a")
        self.assertEqual(m["count"], 1)
        self.assertAlmostEqual(m["mean_error"], 0.2, places=3)

    # ── Adjustment Factor ─────────────────────────────────────────────

    def test_140_adjustment_default_when_no_data(self):
        factor = self.cal.get_adjustment_factor(source="bottleneck")
        self.assertAlmostEqual(factor, 1.0)

    def test_141_adjustment_perfect_accuracy(self):
        self.cal.record_outcome("o1", "bottleneck", "s", 0.5, 0.5, True)
        self.cal.record_outcome("o2", "bottleneck", "s", 0.5, 0.5, True)
        self.cal.record_outcome("o3", "bottleneck", "s", 0.5, 0.5, True)
        factor = self.cal.get_adjustment_factor(source="bottleneck")
        self.assertAlmostEqual(factor, 1.0, places=2)

    def test_142_adjustment_overestimation(self):
        for i in range(5):
            self.cal.record_outcome(f"o_b_{i}", "bottleneck", "s", 0.9, 0.5, True)
        factor = self.cal.get_adjustment_factor(source="bottleneck")
        self.assertLess(factor, 1.0)

    def test_143_adjustment_underestimation(self):
        for i in range(5):
            self.cal.record_outcome(f"o_c_{i}", "ceiling", "s", 0.3, 0.8, True)
        factor = self.cal.get_adjustment_factor(source="ceiling")
        self.assertGreater(factor, 1.0)

    def test_144_adjustment_clamped(self):
        for i in range(10):
            self.cal.record_outcome(f"o_e_{i}", "bottleneck", "s", 1.0, 0.0, False)
        factor = self.cal.get_adjustment_factor(source="bottleneck")
        self.assertGreaterEqual(factor, 0.10)
        self.assertLessEqual(factor, 1.10)

    def test_145_adjustment_prefers_specific_over_global(self):
        # Seed bottleneck + sys_a with overestimation
        for i in range(5):
            self.cal.record_outcome(f"x_{i}", "bottleneck", "sys_a", 0.9, 0.5, True)
        # Specific source+target uses bottleneck+sys_a data
        factor = self.cal.get_adjustment_factor(source="bottleneck", target_system="sys_a")
        self.assertLess(factor, 1.0)
        # Source-only for a source with no data falls back to global
        factor2 = self.cal.get_adjustment_factor(source="principle")
        self.assertNotAlmostEqual(factor2, 1.0, places=4)
        # Unknown source + unknown target → same global fallback
        factor3 = self.cal.get_adjustment_factor(source="principle", target_system="unknown")
        self.assertEqual(factor3, factor2)

    def test_146_get_overall_accuracy_no_data(self):
        self.assertAlmostEqual(self.cal.get_overall_accuracy(), 1.0)

    def test_147_get_overall_accuracy_with_data(self):
        for i in range(5):
            self.cal.record_outcome(f"o_{i}", "b", "s", 0.8, 0.8, True)
        self.assertAlmostEqual(self.cal.get_overall_accuracy(), 1.0, places=2)

    def test_148_get_source_accuracy_no_data(self):
        self.assertAlmostEqual(self.cal.get_source_accuracy("bottleneck"), 1.0)

    def test_149_get_source_accuracy_with_data(self):
        for i in range(5):
            self.cal.record_outcome(f"o_{i}", "bottleneck", "s", 0.8, 0.8, True)
        acc = self.cal.get_source_accuracy("bottleneck")
        self.assertAlmostEqual(acc, 1.0, places=2)

    def test_150_list_source_accuracies_empty(self):
        self.assertEqual(self.cal.list_source_accuracies(), {})

    def test_151_list_source_accuracies_with_data(self):
        for i in range(5):
            self.cal.record_outcome(f"o_b_{i}", "bottleneck", "s", 0.5, 0.5, True)
        for i in range(5):
            self.cal.record_outcome(f"o_c_{i}", "ceiling", "s", 0.5, 0.5, True)
        accs = self.cal.list_source_accuracies()
        self.assertIn("bottleneck", accs)
        self.assertIn("ceiling", accs)
        self.assertAlmostEqual(accs["bottleneck"], 1.0, places=2)

    def test_152_source_with_insufficient_data_excluded(self):
        self.cal.record_outcome("o", "bottleneck", "s", 0.5, 0.5, True)
        accs = self.cal.list_source_accuracies()
        self.assertEqual(accs, {})


# ── Phase 17.1 — Integration Tests ────────────────────────────────────


class TestOpportunityCalibratorIntegration(unittest.TestCase):
    """Calibrator wired into OpportunityDiscoveryEngine."""

    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.store = OpportunityStore(db_path=self.tmp)
        self.cal = OpportunityCalibrator(store=self.store)

    def tearDown(self):
        self.store.clear()
        os.remove(self.tmp)

    def test_160_engine_without_calibrator_produces_unchanged_scores(self):
        engine_no_cal = OpportunityDiscoveryEngine()
        opps = engine_no_cal.discover_all()
        self.assertGreater(len(opps), 0)
        for opp in opps:
            self.assertAlmostEqual(opp.calibration_accuracy, 1.0)

    def test_161_engine_with_calibrator_no_data_produces_neutral(self):
        engine = OpportunityDiscoveryEngine(calibrator=self.cal)
        opps = engine.discover_all()
        self.assertGreater(len(opps), 0)
        for opp in opps:
            self.assertAlmostEqual(opp.calibration_accuracy, 1.0)

    def test_162_calibrator_reduces_scores_for_overestimating_source(self):
        # Seed calibrator with overestimation data for ceiling source
        for i in range(5):
            self.cal.record_outcome(f"o_{i}", "ceiling", "sys", 0.9, 0.5, True)

        engine = OpportunityDiscoveryEngine(calibrator=self.cal)
        opps = engine.discover_all()
        ceiling_opps = [o for o in opps if o.source == OpportunitySource.CEILING]
        if ceiling_opps:
            self.assertLess(ceiling_opps[0].calibration_accuracy, 1.0)

    def test_163_calibrator_does_not_affect_other_sources(self):
        for _ in range(5):
            self.cal.record_outcome("o", "ceiling", "sys", 0.9, 0.5, True)

        engine = OpportunityDiscoveryEngine(calibrator=self.cal)
        opps = engine.discover_all()
        bottleneck_opps = [o for o in opps if o.source == OpportunitySource.BOTTLENECK]
        for opp in bottleneck_opps:
            self.assertAlmostEqual(opp.calibration_accuracy, 1.0)

    def test_164_calibrator_formula_is_5_dimensional(self):
        for _ in range(5):
            self.cal.record_outcome("o", "ceiling", "sys", 0.9, 0.5, True)

        engine = OpportunityDiscoveryEngine(calibrator=self.cal)
        opps = engine.discover_all()

        # Check that score = impact * headroom * prob * confidence * cal
        for opp in opps:
            expected_raw = opp.bottleneck_impact * opp.improvement_headroom * opp.success_probability * opp.confidence
            if opp.calibration_accuracy != 1.0:
                self.assertAlmostEqual(
                    opp.opportunity_score,
                    expected_raw * opp.calibration_accuracy,
                    places=2,
                )
            else:
                self.assertAlmostEqual(
                    opp.opportunity_score,
                    expected_raw,
                    places=3,
                )
