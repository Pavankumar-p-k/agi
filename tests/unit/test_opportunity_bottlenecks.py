"""Architectural Bottleneck Prediction tests — Phase 22.

Covers:
  - BottleneckImpact + Bottleneck models
  - impact_ratio computation
  - _compute_local_impacts (no data, with activity store, with scores)
  - _aggregate_tool_stats
  - _tool_stat_impact matching
  - _compute_bottleneck propagation (linear chain, fan-out, isolated)
  - analyze() on default graph
  - Edge cases (empty graph, single node, no edges)
"""

import unittest
from unittest.mock import MagicMock

from core.opportunity.bottlenecks import (
    DEFAULT_LOCAL_IMPACT,
    MIN_REPORTABLE_IMPACT,
    Bottleneck,
    BottleneckAnalyzer,
    BottleneckImpact,
)
from core.opportunity.graph import (
    OpportunityGraph,
    OpportunityGraphEdge,
    build_default_graph,
)


# ── Model Tests ───────────────────────────────────────────────────────


class TestBottleneckImpact(unittest.TestCase):

    def test_01_default_values(self):
        bi = BottleneckImpact("target_A", 0.8, 0.15)
        self.assertEqual(bi.target_system, "target_A")
        self.assertAlmostEqual(bi.edge_confidence, 0.8)
        self.assertAlmostEqual(bi.propagated_fraction, 0.15)


class TestBottleneck(unittest.TestCase):

    def setUp(self):
        self.bn = Bottleneck(
            subsystem="browser_automation",
            local_impact=0.4,
            propagated_impact=0.6,
            total_constrained_value=1.0,
            confidence=0.85,
            affected_systems=[
                BottleneckImpact("benchmark", 0.5, 0.3),
                BottleneckImpact("calibration", 0.4, 0.2),
            ],
            depth_reach=2,
            evidence=["Local: 0.40", "Propagated: 0.60"],
        )

    def test_10_impact_ratio(self):
        self.assertAlmostEqual(self.bn.impact_ratio, 1.5)

    def test_11_impact_ratio_zero_local(self):
        bn = Bottleneck("test", local_impact=0.0, propagated_impact=0.5,
                        total_constrained_value=0.5, confidence=0.5)
        self.assertAlmostEqual(bn.impact_ratio, 0.0)

    def test_12_to_dict(self):
        d = self.bn.to_dict()
        self.assertEqual(d["subsystem"], "browser_automation")
        self.assertAlmostEqual(d["local_impact"], 0.4)
        self.assertAlmostEqual(d["propagated_impact"], 0.6)
        self.assertAlmostEqual(d["impact_ratio"], 1.5)
        self.assertEqual(len(d["affected_systems"]), 2)

    def test_13_to_dict_includes_confidence(self):
        d = self.bn.to_dict()
        self.assertAlmostEqual(d["confidence"], 0.85)

    def test_14_to_dict_empty_affected(self):
        bn = Bottleneck("test", 0.3, 0.0, 0.3, 0.5)
        d = bn.to_dict()
        self.assertEqual(d["affected_systems"], [])


# ── Local Impact Tests ────────────────────────────────────────────────


class TestComputeLocalImpacts(unittest.TestCase):

    def setUp(self):
        self.analyzer = BottleneckAnalyzer()

    def test_20_default_graph_no_store(self):
        """Without any data source, uses DEFAULT_LOCAL_IMPACT."""
        graph = build_default_graph()
        impacts = self.analyzer._compute_local_impacts(graph)
        for name in graph.nodes:
            self.assertIn(name, impacts)
        # Some nodes match DEFAULT_SYSTEM_SCORES
        self.assertGreater(impacts.get("browser_automation", 0), 0.02)
        self.assertGreater(impacts.get("self_modification", 0), 0.02)

    def test_21_with_system_scores(self):
        graph = build_default_graph()
        scores = {"browser_automation": 0.5, "self_modification": 0.3}
        impacts = self.analyzer._compute_local_impacts(graph, system_scores=scores)
        self.assertAlmostEqual(impacts["browser_automation"], 0.5)
        self.assertAlmostEqual(impacts["self_modification"], 0.7)

    def test_22_scores_not_in_graph_ignored(self):
        """Scores for nodes not in the graph are not added."""
        graph = OpportunityGraph()
        graph.add_node("only_node")
        impacts = self.analyzer._compute_local_impacts(
            graph, system_scores={"nonexistent": 0.1}
        )
        self.assertIn("only_node", impacts)
        self.assertNotIn("nonexistent", impacts)

    def test_23_empty_graph_returns_empty(self):
        graph = OpportunityGraph()
        impacts = self.analyzer._compute_local_impacts(graph)
        self.assertEqual(impacts, {})

    def test_24_default_impact_for_unknown_system(self):
        """Systems not in DEFAULT_SYSTEM_SCORES get DEFAULT_LOCAL_IMPACT."""
        graph = OpportunityGraph()
        graph.add_node("completely_new_system")
        impacts = self.analyzer._compute_local_impacts(graph)
        self.assertAlmostEqual(
            impacts["completely_new_system"], DEFAULT_LOCAL_IMPACT
        )


# ── Tool Stats Tests ──────────────────────────────────────────────────


class TestToolStats(unittest.TestCase):

    def setUp(self):
        self.analyzer = BottleneckAnalyzer()

    def _make_tool_node(self, label: str, status: str = "COMPLETED") -> MagicMock:
        node = MagicMock()
        node.label = label
        node.status = status
        return node

    def test_30_aggregate_tool_stats(self):
        store = MagicMock()
        store.get_nodes_by_type.return_value = [
            self._make_tool_node("browser_navigate"),
            self._make_tool_node("browser_navigate", "FAILED"),
            self._make_tool_node("build_project"),
        ]
        stats = self.analyzer._aggregate_tool_stats(store)
        self.assertIn("browser_navigate", stats)
        self.assertIn("build_project", stats)
        self.assertEqual(stats["browser_navigate"]["total"], 2)
        self.assertEqual(stats["browser_navigate"]["successes"], 1)
        self.assertEqual(stats["browser_navigate"]["failures"], 1)

    def test_31_empty_store(self):
        store = MagicMock()
        store.get_nodes_by_type.return_value = []
        stats = self.analyzer._aggregate_tool_stats(store)
        self.assertEqual(stats, {})

    def test_32_no_label_skipped(self):
        store = MagicMock()
        node = MagicMock()
        node.label = ""
        node.status = "COMPLETED"
        store.get_nodes_by_type.return_value = [node]
        stats = self.analyzer._aggregate_tool_stats(store)
        self.assertEqual(stats, {})

    def test_33_tool_stat_impact_matched(self):
        stats = {
            "browser_navigate": {"successes": 3, "failures": 7, "total": 10},
            "browser_click": {"successes": 8, "failures": 2, "total": 10},
        }
        impact = self.analyzer._tool_stat_impact("browser_automation", stats)
        # Total: 20, failures: 9 → failure_rate = 0.45
        self.assertIsNotNone(impact)
        self.assertAlmostEqual(impact, 0.45, places=2)

    def test_34_tool_stat_impact_no_match(self):
        stats = {"unrelated_tool": {"successes": 10, "failures": 0, "total": 10}}
        impact = self.analyzer._tool_stat_impact("browser_automation", stats)
        self.assertIsNone(impact)

    def test_35_tool_stat_impact_insufficient_data(self):
        stats = {"browser_navigate": {"successes": 1, "failures": 1, "total": 2}}
        impact = self.analyzer._tool_stat_impact("browser_automation", stats)
        self.assertIsNone(impact)  # total < 3


# ── Bottleneck Propagation Tests ──────────────────────────────────────


class TestComputeBottleneck(unittest.TestCase):

    def setUp(self):
        self.analyzer = BottleneckAnalyzer(depth_discount=0.5)

    def test_40_isolated_node_no_propagation(self):
        """A node with no outgoing edges has zero propagated impact."""
        graph = OpportunityGraph()
        graph.add_node("isolated")
        impacts = {"isolated": 0.5}
        bn = self.analyzer._compute_bottleneck(graph, "isolated", impacts)
        self.assertIsNotNone(bn)
        self.assertAlmostEqual(bn.local_impact, 0.5)
        self.assertAlmostEqual(bn.propagated_impact, 0.0)
        self.assertAlmostEqual(bn.total_constrained_value, 0.5)

    def test_41_linear_chain_propagation(self):
        """A -> B -> C: A's propagated impact includes B and C with discount."""
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("B", "C", confidence=0.8))
        impacts = {"A": 0.5, "B": 0.3, "C": 0.2}

        bn = self.analyzer._compute_bottleneck(graph, "A", impacts)
        # B: 0.3 * 0.8 * 1.0 = 0.24
        # C: 0.2 * (0.8*0.8) * 0.5 = 0.2 * 0.64 * 0.5 = 0.064
        # Total: 0.24 + 0.064 = 0.304
        self.assertAlmostEqual(bn.propagated_impact, 0.304, places=3)
        self.assertEqual(bn.depth_reach, 2)
        self.assertEqual(len(bn.affected_systems), 2)

    def test_42_fan_out_propagation(self):
        """A -> B, A -> C: A constrains both B and C directly."""
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.9))
        graph.add_edge(OpportunityGraphEdge("A", "C", confidence=0.7))
        impacts = {"A": 0.5, "B": 0.4, "C": 0.3}

        bn = self.analyzer._compute_bottleneck(graph, "A", impacts)
        # B: 0.4 * 0.9 * 1.0 = 0.36
        # C: 0.3 * 0.7 * 1.0 = 0.21
        # Total: 0.57
        self.assertAlmostEqual(bn.propagated_impact, 0.57, places=3)

    def test_43_low_confidence_edge_skipped(self):
        """Edges below MIN_EDGE_CONFIDENCE are skipped in propagation."""
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.05))
        impacts = {"A": 0.5, "B": 0.8}

        bn = self.analyzer._compute_bottleneck(graph, "A", impacts)
        self.assertAlmostEqual(bn.propagated_impact, 0.0)

    def test_44_cycle_does_not_infinite_loop(self):
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("B", "A", confidence=0.8))
        impacts = {"A": 0.5, "B": 0.3}

        bn = self.analyzer._compute_bottleneck(graph, "A", impacts)
        # Should not infinite loop
        self.assertIsNotNone(bn)
        self.assertGreaterEqual(bn.propagated_impact, 0.0)

    def test_45_zero_local_impact_returns_none(self):
        graph = OpportunityGraph()
        graph.add_node("zero")
        impacts = {"zero": 0.0}
        bn = self.analyzer._compute_bottleneck(graph, "zero", impacts)
        self.assertIsNone(bn)

    def test_46_confidence_scoring_data_supported(self):
        graph = OpportunityGraph()
        graph.add_node("test")
        impacts = {"test": 0.6}  # > DEFAULT_LOCAL_IMPACT + 0.05
        bn = self.analyzer._compute_bottleneck(graph, "test", impacts)
        # base 0.50 + 0.20 data bonus
        self.assertAlmostEqual(bn.confidence, 0.70)

    def test_47_confidence_scoring_with_propagation(self):
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        impacts = {"A": 0.6, "B": 0.3}
        bn = self.analyzer._compute_bottleneck(graph, "A", impacts)
        # base 0.50 + 0.20 data + 0.15 propagation
        self.assertAlmostEqual(bn.confidence, 0.85)


# ── Full Analysis Tests ───────────────────────────────────────────────


class TestAnalyze(unittest.TestCase):

    def setUp(self):
        self.analyzer = BottleneckAnalyzer(depth_discount=0.5)

    def test_50_empty_graph_returns_empty(self):
        graph = OpportunityGraph()
        results = self.analyzer.analyze(graph)
        self.assertEqual(results, [])

    def test_51_default_graph_returns_ranked_bottlenecks(self):
        graph = build_default_graph()
        results = self.analyzer.analyze(graph)
        self.assertGreater(len(results), 0)
        # Results should be sorted by total_constrained_value descending
        for i in range(len(results) - 1):
            self.assertGreaterEqual(
                results[i].total_constrained_value,
                results[i + 1].total_constrained_value,
            )

    def test_52_single_node_no_edges(self):
        graph = OpportunityGraph()
        graph.add_node("lonely")
        results = self.analyzer.analyze(graph)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].subsystem, "lonely")
        self.assertAlmostEqual(results[0].propagated_impact, 0.0)

    def test_53_bottleneck_ordering(self):
        """A high-impact root with many dependents ranks above isolated nodes."""
        graph = OpportunityGraph()
        # Root A constrains B and C
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.9))
        graph.add_edge(OpportunityGraphEdge("A", "C", confidence=0.9))
        # Isolated D
        graph.add_node("D")
        # Override scores
        scores = {"A": 0.5, "B": 0.3, "C": 0.3, "D": 0.8}

        results = self.analyzer.analyze(graph, system_scores=scores)
        self.assertGreater(len(results), 0)
        # A should rank higher than D because A's propagated impact > 0
        a = next(r for r in results if r.subsystem == "A")
        d = next(r for r in results if r.subsystem == "D")
        self.assertGreater(a.total_constrained_value, d.total_constrained_value)

    def test_54_min_impact_filter(self):
        """Systems below MIN_REPORTABLE_IMPACT are excluded."""
        graph = OpportunityGraph()
        graph.add_node("tiny")
        results = self.analyzer.analyze(
            graph, system_scores={"tiny": 0.99}
        )
        # local_impact = 0.01, which is below 0.05
        tiny = [r for r in results if r.subsystem == "tiny"]
        self.assertEqual(len(tiny), 0)

    def test_55_all_nodes_have_evidence(self):
        graph = build_default_graph()
        results = self.analyzer.analyze(graph)
        for bn in results:
            self.assertGreater(len(bn.evidence), 0)

    def test_56_propagated_impact_via_chain(self):
        """Medium chain test: opportunity_discovery -> self_modification -> build_benchmark"""
        graph = build_default_graph()
        scores = {
            "opportunity_discovery": 0.6,
            "self_modification": 0.5,
            "build_benchmark": 0.3,
        }
        results = self.analyzer.analyze(graph, system_scores=scores)
        od = next(r for r in results if r.subsystem == "opportunity_discovery")
        self.assertGreater(od.propagated_impact, 0.0)

    def test_57_analyze_with_activity_store(self):
        """analyze() works with activity store for tool-based impact."""
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("browser_automation", "automated_build", confidence=0.5))

        store = MagicMock()
        store.get_nodes_by_type.return_value = []
        results = self.analyzer.analyze(graph, activity_store=store)
        self.assertGreater(len(results), 0)


# ── Integration Tests ─────────────────────────────────────────────────


class TestIntegration(unittest.TestCase):

    def test_60_end_to_end_with_builder(self):
        """Full pipeline: builder produces graph, analyzer finds bottlenecks."""
        from core.opportunity.graph import OpportunityGraphBuilder
        from core.opportunity.models import Opportunity, OpportunitySource, OpportunityStatus
        from datetime import datetime, timezone

        builder = OpportunityGraphBuilder()
        opps = [
            Opportunity(
                id="test_1", target_system="browser_automation",
                improvement_description="fix browser",
                source=OpportunitySource.CEILING,
                bottleneck_impact=0.6, improvement_headroom=0.4,
                success_probability=0.5, confidence=0.5,
                opportunity_score=0.06, rationale="test",
                status=OpportunityStatus.OPEN,
                created_at=datetime.now(timezone.utc),
            ),
        ]
        graph = builder.build(opps)
        analyzer = BottleneckAnalyzer()
        results = analyzer.analyze(graph)
        self.assertGreater(len(results), 0)
        # browser_automation should be in the results
        ba = next((r for r in results if r.subsystem == "browser_automation"), None)
        self.assertIsNotNone(ba)

    def test_61_impact_ratio_highlights_leverage(self):
        """A high impact_ratio means high-leverage improvement target."""
        graph = OpportunityGraph()
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.9))
        graph.add_edge(OpportunityGraphEdge("B", "C", confidence=0.9))
        graph.add_edge(OpportunityGraphEdge("C", "D", confidence=0.9))
        scores = {"A": 0.2, "B": 0.1, "C": 0.1, "D": 0.1}

        results = BottleneckAnalyzer(0.5).analyze(graph, system_scores=scores)
        a = next(r for r in results if r.subsystem == "A")
        # Even though A has low local impact, it constrains B, C, D
        self.assertGreater(a.impact_ratio, 1.0)

    def test_62_exported_via_init(self):
        from core.opportunity import Bottleneck, BottleneckAnalyzer, BottleneckImpact
        self.assertIsNotNone(Bottleneck)
        self.assertIsNotNone(BottleneckAnalyzer)
        self.assertIsNotNone(BottleneckImpact)
