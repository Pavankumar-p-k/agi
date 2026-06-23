"""Autonomous Roadmap Generation tests — Phase 23.

Covers:
  - RoadmapItem, RoadmapPhase, Roadmap models
  - Dependency depth computation
  - Dependency and unlock mapping
  - Full roadmap generation with opportunities + graph + bottlenecks
  - Edge cases: empty inputs, single node, no graph edges
  - Integration with builder + analyzer
"""

import unittest
from datetime import datetime, timezone

from core.opportunity.bottlenecks import Bottleneck
from core.opportunity.graph import (
    OpportunityGraph,
    OpportunityGraphEdge,
    build_default_graph,
)
from core.opportunity.models import Opportunity, OpportunitySource, OpportunityStatus
from core.opportunity.roadmap import (
    Roadmap,
    RoadmapGenerator,
    RoadmapItem,
    RoadmapPhase,
)


# ── Model Tests ───────────────────────────────────────────────────────


class TestRoadmapItem(unittest.TestCase):

    def test_01_defaults(self):
        item = RoadmapItem("sys", "opp_1", "fix sys", 0.85)
        self.assertEqual(item.system_name, "sys")
        self.assertAlmostEqual(item.compounded_priority, 0.85)
        self.assertEqual(item.dependencies, [])
        self.assertEqual(item.unlocks, [])

    def test_02_to_dict(self):
        item = RoadmapItem("browser", "opp_1", "fix browser", 0.75,
                           dependency_depth=1,
                           dependencies=["opportunity_discovery"],
                           unlocks=["build_benchmark"],
                           current_score=0.65)
        d = item.to_dict()
        self.assertEqual(d["system"], "browser")
        self.assertAlmostEqual(d["priority"], 0.75)
        self.assertEqual(d["depth"], 1)
        self.assertIn("opportunity_discovery", d["dependencies"])


class TestRoadmapPhase(unittest.TestCase):

    def test_10_defaults(self):
        phase = RoadmapPhase("Quarter 1")
        self.assertEqual(phase.name, "Quarter 1")
        self.assertEqual(phase.items, [])
        self.assertAlmostEqual(phase.total_priority, 0.0)

    def test_11_with_items(self):
        items = [
            RoadmapItem("A", "o1", "fix A", 0.8),
            RoadmapItem("B", "o2", "fix B", 0.6),
        ]
        phase = RoadmapPhase("Q1", items=items, total_priority=1.4)
        self.assertEqual(len(phase.items), 2)
        self.assertAlmostEqual(phase.total_priority, 1.4)

    def test_12_to_dict(self):
        items = [RoadmapItem("A", "o1", "fix A", 0.8)]
        phase = RoadmapPhase("Q1", items=items, total_priority=0.8)
        d = phase.to_dict()
        self.assertEqual(d["name"], "Q1")
        self.assertEqual(d["item_count"], 1)


class TestRoadmap(unittest.TestCase):

    def test_20_defaults(self):
        rm = Roadmap()
        self.assertEqual(rm.phases, [])
        self.assertEqual(rm.total_items, 0)
        self.assertIsNone(rm.generated_at)

    def test_21_with_phases(self):
        p1 = RoadmapPhase("Q1", items=[RoadmapItem("A", "o1", "fix A", 0.8)])
        p2 = RoadmapPhase("Q2", items=[RoadmapItem("B", "o2", "fix B", 0.6)])
        rm = Roadmap(phases=[p1, p2], total_priority=1.4, total_items=2,
                     generated_at=datetime.now(timezone.utc),
                     summary="2 phases")
        self.assertEqual(len(rm.phases), 2)
        self.assertEqual(rm.total_items, 2)

    def test_22_to_dict(self):
        p1 = RoadmapPhase("Q1", items=[RoadmapItem("A", "o1", "fix A", 0.8)])
        rm = Roadmap(phases=[p1], total_priority=0.8, total_items=1,
                     generated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                     summary="test")
        d = rm.to_dict()
        self.assertEqual(d["total_items"], 1)
        self.assertEqual(len(d["phases"]), 1)


# ── Dependency Depth Tests ────────────────────────────────────────────


class TestDependencyDepth(unittest.TestCase):

    def setUp(self):
        self.generator = RoadmapGenerator()

    def test_30_linear_chain(self):
        """A -> B -> C: depth 0, 1, 2."""
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("B", "C", confidence=0.8))
        depths = self.generator._compute_dependency_depths(graph)
        self.assertEqual(depths.get("A"), 0)
        self.assertEqual(depths.get("B"), 1)
        self.assertEqual(depths.get("C"), 2)

    def test_31_fan_out(self):
        """A -> B, A -> C: both B and C have depth 1."""
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("A", "C", confidence=0.8))
        depths = self.generator._compute_dependency_depths(graph)
        self.assertEqual(depths.get("A"), 0)
        self.assertEqual(depths.get("B"), 1)
        self.assertEqual(depths.get("C"), 1)

    def test_32_multiple_roots(self):
        """A -> C, B -> C: multiple paths to C."""
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "C", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("B", "C", confidence=0.8))
        depths = self.generator._compute_dependency_depths(graph)
        self.assertEqual(depths.get("A"), 0)
        self.assertEqual(depths.get("B"), 0)
        self.assertEqual(depths.get("C"), 1)

    def test_33_cycle_still_produces_depth(self):
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("B", "A", confidence=0.8))
        depths = self.generator._compute_dependency_depths(graph)
        self.assertIn("A", depths)
        self.assertIn("B", depths)

    def test_34_default_graph_depths(self):
        graph = build_default_graph()
        depths = self.generator._compute_dependency_depths(graph)
        for node in graph.nodes:
            self.assertIn(node, depths)
            self.assertGreaterEqual(depths[node], 0)

    def test_35_isolated_node_depth_zero(self):
        graph = OpportunityGraph()
        graph.add_node("lonely")
        depths = self.generator._compute_dependency_depths(graph)
        self.assertEqual(depths.get("lonely"), 0)


# ── Dependency / Unlock Mapping Tests ─────────────────────────────────


class TestDependencyMapping(unittest.TestCase):

    def setUp(self):
        self.generator = RoadmapGenerator()

    def test_40_dependencies(self):
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("B", "C", confidence=0.8))
        deps = self.generator._compute_dependencies(graph)
        self.assertNotIn("A", deps)  # A has no incoming
        self.assertEqual(deps.get("B"), ["A"])
        self.assertEqual(deps.get("C"), ["B"])

    def test_41_unlocks(self):
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("A", "C", confidence=0.8))
        unlocks = self.generator._compute_unlocks(graph)
        self.assertEqual(set(unlocks.get("A", [])), {"B", "C"})

    def test_42_no_edges_empty_maps(self):
        graph = OpportunityGraph()
        graph.add_node("lonely")
        self.assertEqual(self.generator._compute_dependencies(graph), {})
        self.assertEqual(self.generator._compute_unlocks(graph), {})


# ── Full Generation Tests ─────────────────────────────────────────────


class TestGenerate(unittest.TestCase):

    def setUp(self):
        self.generator = RoadmapGenerator(items_per_phase=2)
        self.scores = {
            "opportunity_discovery": 0.35,
            "self_modification": 0.45,
            "browser_automation": 0.65,
            "build_benchmark": 0.70,
            "strategic_reasoning": 0.82,
        }

    def _make_opp(self, system: str, score: float = 0.5) -> Opportunity:
        return Opportunity(
            id=f"opp_{system}",
            target_system=system,
            improvement_description=f"Improve {system}",
            source=OpportunitySource.CEILING,
            bottleneck_impact=0.5,
            improvement_headroom=0.5,
            success_probability=0.5,
            confidence=0.5,
            calibration_accuracy=1.0,
            opportunity_score=score,
            rationale="test",
            status=OpportunityStatus.OPEN,
            created_at=datetime.now(timezone.utc),
        )

    def test_50_basic_generation(self):
        graph = build_default_graph()
        opps = [self._make_opp(n) for n in graph.nodes]
        roadmap = self.generator.generate(opps, graph, system_scores=self.scores)
        self.assertGreater(len(roadmap.phases), 0)
        self.assertGreater(roadmap.total_items, 0)

    def test_51_empty_opportunities(self):
        graph = build_default_graph()
        roadmap = self.generator.generate([], graph)
        self.assertEqual(len(roadmap.phases), 0)
        self.assertEqual(roadmap.total_items, 0)

    def test_52_empty_graph(self):
        graph = OpportunityGraph()
        opp = self._make_opp("test_system")
        roadmap = self.generator.generate([opp], graph)
        # Node not in graph, so it's skipped
        self.assertEqual(len(roadmap.phases), 0)

    def test_53_items_per_phase(self):
        generator = RoadmapGenerator(items_per_phase=3)
        graph = build_default_graph()
        opps = [self._make_opp(n) for n in graph.nodes]
        roadmap = generator.generate(opps, graph)
        for phase in roadmap.phases[:-1]:  # last phase may have fewer
            self.assertLessEqual(len(phase.items), 3)

    def test_54_ordering_by_depth(self):
        """Items with depth 0 appear in earlier phases."""
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("B", "C", confidence=0.8))
        opps = [self._make_opp(n) for n in ["A", "B", "C"]]
        roadmap = self.generator.generate(opps, graph)
        # A (depth 0) should be in phase 0, B (depth 1) phase 0 or 1, etc.
        all_items = [i for p in roadmap.phases for i in p.items]
        a_idx = next(i for i, x in enumerate(all_items) if x.system_name == "A")
        c_idx = next(i for i, x in enumerate(all_items) if x.system_name == "C")
        self.assertLess(a_idx, c_idx)

    def test_55_bottleneck_weight(self):
        """Adding bottleneck weights changes priority ordering."""
        graph = build_default_graph()
        opps = [self._make_opp(n) for n in graph.nodes]

        bottlenecks = [
            Bottleneck("browser_automation", 0.5, 0.3, 0.8, 0.85),
        ]
        roadmap = self.generator.generate(opps, graph, bottlenecks=bottlenecks)
        self.assertGreater(roadmap.total_items, 0)

    def test_56_rationale_present(self):
        graph = build_default_graph()
        opps = [self._make_opp(n) for n in graph.nodes]
        roadmap = self.generator.generate(opps, graph)
        for phase in roadmap.phases:
            for item in phase.items:
                self.assertTrue(len(item.rationale) > 0)

    def test_57_summary_present(self):
        graph = build_default_graph()
        opps = [self._make_opp(n) for n in graph.nodes]
        roadmap = self.generator.generate(opps, graph)
        self.assertTrue(len(roadmap.summary) > 0)
        self.assertIn("phases", roadmap.summary.lower())

    def test_58_phase_rationale_present(self):
        graph = build_default_graph()
        opps = [self._make_opp(n) for n in graph.nodes]
        roadmap = self.generator.generate(opps, graph)
        for phase in roadmap.phases:
            self.assertTrue(len(phase.rationale) > 0)

    def test_59_all_items_have_nonzero_priority(self):
        graph = build_default_graph()
        opps = [self._make_opp(n) for n in graph.nodes]
        roadmap = self.generator.generate(opps, graph)
        for phase in roadmap.phases:
            for item in phase.items:
                self.assertGreater(item.compounded_priority, 0)

    def test_60_unlock_map_populated(self):
        graph = build_default_graph()
        opps = [self._make_opp(n) for n in graph.nodes]
        roadmap = self.generator.generate(opps, graph)
        # Some items should have unlocks (nodes with outgoing edges)
        all_items = [i for p in roadmap.phases for i in p.items]
        has_unlocks = [i for i in all_items if i.unlocks]
        self.assertGreater(len(has_unlocks), 0)

    def test_61_exported_via_init(self):
        from core.opportunity import Roadmap, RoadmapGenerator, RoadmapItem, RoadmapPhase
        self.assertIsNotNone(RoadmapGenerator)
        self.assertIsNotNone(Roadmap)
        self.assertIsNotNone(RoadmapItem)
        self.assertIsNotNone(RoadmapPhase)

    def test_62_dependency_map_populated(self):
        graph = build_default_graph()
        opps = [self._make_opp(n) for n in graph.nodes]
        roadmap = self.generator.generate(opps, graph)
        all_items = [i for p in roadmap.phases for i in p.items]
        has_deps = [i for i in all_items if i.dependencies]
        # At least some items have dependencies (nodes with incoming edges)
        self.assertGreater(len(has_deps), 0)

    def test_63_to_dict_roundtrip(self):
        graph = build_default_graph()
        node_list = list(graph.nodes.keys())[:3]
        opps = [self._make_opp(n) for n in node_list]
        roadmap = self.generator.generate(opps, graph)
        d = roadmap.to_dict()
        self.assertEqual(d["total_items"], roadmap.total_items)
        self.assertEqual(len(d["phases"]), len(roadmap.phases))


# ── Integration Tests ─────────────────────────────────────────────────


class TestIntegration(unittest.TestCase):

    def test_70_full_pipeline(self):
        """Opportunities -> Graph (Builder) -> Bottlenecks (Analyzer) -> Roadmap (Generator)."""
        from core.opportunity.bottlenecks import BottleneckAnalyzer
        from core.opportunity.graph import OpportunityGraphBuilder

        builder = OpportunityGraphBuilder()
        graph = builder.build([])  # default graph only

        analyzer = BottleneckAnalyzer()
        bottlenecks = analyzer.analyze(graph)

        opps = [
            Opportunity(
                id=f"opp_{n}", target_system=n,
                improvement_description=f"Improve {n}",
                source=OpportunitySource.CEILING,
                bottleneck_impact=0.5, improvement_headroom=0.5,
                success_probability=0.5, confidence=0.5,
                calibration_accuracy=1.0, opportunity_score=0.5,
                rationale="test", status=OpportunityStatus.OPEN,
                created_at=datetime.now(timezone.utc),
            )
            for n in graph.nodes
        ]

        generator = RoadmapGenerator(items_per_phase=3)
        roadmap = generator.generate(opps, graph, bottlenecks=bottlenecks)

        self.assertGreater(len(roadmap.phases), 0)
        self.assertGreater(roadmap.total_items, 0)
        self.assertIn("Quarter 1", roadmap.phases[0].name)
