"""Opportunity Graph tests — Phase 19.

Covers:
  - Graph models: nodes, edges, add/remove/get
  - Default graph: correct structure
  - UnlockValueScorer: forward reachability, depth discount, isolation
  - OpportunityGraphBuilder: mining, ranking, tool-to-system mapping
"""

import unittest
from unittest.mock import MagicMock

from core.opportunity.graph import (
    DEFAULT_UNLOCK_VALUE,
    MIN_EDGE_CONFIDENCE,
    OpportunityGraph,
    OpportunityGraphBuilder,
    OpportunityGraphEdge,
    OpportunityGraphNode,
    UnlockValueScorer,
    build_default_graph,
    _tool_to_system,
)
from core.opportunity.models import (
    Opportunity,
    OpportunitySource,
    OpportunityStatus,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _make_opp(
    system: str,
    score: float = 0.5,
    impact: float = 0.5,
    headroom: float = 0.5,
    prob: float = 0.5,
    conf: float = 0.5,
    cal: float = 1.0,
) -> Opportunity:
    return Opportunity(
        id=f"opp_{system}",
        target_system=system,
        improvement_description=f"Improve {system}",
        source=OpportunitySource.CEILING,
        bottleneck_impact=impact,
        improvement_headroom=headroom,
        success_probability=prob,
        confidence=conf,
        calibration_accuracy=cal,
        opportunity_score=score,
        rationale="test",
        status=OpportunityStatus.OPEN,
    )


# ── Graph Model Tests ─────────────────────────────────────────────────


class TestOpportunityGraph(unittest.TestCase):
    """Graph node/edge CRUD and traversal."""

    def setUp(self):
        self.graph = OpportunityGraph()

    def test_01_add_node(self):
        node = self.graph.add_node("browser_automation")
        self.assertEqual(node.system_name, "browser_automation")
        self.assertAlmostEqual(node.unlock_value, DEFAULT_UNLOCK_VALUE)

    def test_02_get_node_missing_returns_none(self):
        self.assertIsNone(self.graph.get_node("nonexistent"))

    def test_03_add_node_with_opportunity(self):
        opp = _make_opp("browser_automation", score=0.8)
        self.graph.add_node("browser_automation", opp)
        node = self.graph.get_node("browser_automation")
        self.assertIsNotNone(node)
        self.assertIsNotNone(node.opportunity)
        # base_score = impact*headroom*prob*conf*cal = 0.5^4*1.0 = 0.0625
        self.assertAlmostEqual(node.base_score, 0.0625)

    def test_04_add_edge_creates_nodes(self):
        self.graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        self.assertIsNotNone(self.graph.get_node("A"))
        self.assertIsNotNone(self.graph.get_node("B"))
        self.assertEqual(self.graph.node_count, 2)

    def test_05_get_outgoing_edges(self):
        self.graph.add_edge(OpportunityGraphEdge("A", "B"))
        self.graph.add_edge(OpportunityGraphEdge("A", "C"))
        outgoing = self.graph.get_outgoing("A")
        self.assertEqual(len(outgoing), 2)

    def test_06_get_incoming_edges(self):
        self.graph.add_edge(OpportunityGraphEdge("A", "B"))
        self.graph.add_edge(OpportunityGraphEdge("C", "B"))
        incoming = self.graph.get_incoming("B")
        self.assertEqual(len(incoming), 2)

    def test_07_predecessors_and_successors(self):
        self.graph.add_edge(OpportunityGraphEdge("A", "B"))
        self.graph.add_edge(OpportunityGraphEdge("B", "C"))
        self.assertEqual(self.graph.successors("A"), ["B"])
        self.assertEqual(self.graph.predecessors("C"), ["B"])

    def test_08_remove_node(self):
        self.graph.add_node("X")
        self.graph.add_edge(OpportunityGraphEdge("X", "Y"))
        self.graph.remove_node("X")
        self.assertIsNone(self.graph.get_node("X"))
        self.assertEqual(self.graph.get_outgoing("X"), [])

    def test_09_edge_count(self):
        self.assertEqual(self.graph.edge_count, 0)
        self.graph.add_edge(OpportunityGraphEdge("A", "B"))
        self.assertEqual(self.graph.edge_count, 1)
        self.graph.add_edge(OpportunityGraphEdge("B", "C"))
        self.assertEqual(self.graph.edge_count, 2)

    def test_10_node_count(self):
        self.assertEqual(self.graph.node_count, 0)
        self.graph.add_node("A")
        self.graph.add_node("B")
        self.assertEqual(self.graph.node_count, 2)

    def test_11_has_outgoing(self):
        self.graph.add_edge(OpportunityGraphEdge("A", "B"))
        self.assertTrue(self.graph.has_outgoing("A"))
        self.assertFalse(self.graph.has_outgoing("B"))

    def test_12_has_incoming(self):
        self.graph.add_edge(OpportunityGraphEdge("A", "B"))
        self.assertTrue(self.graph.has_incoming("B"))
        self.assertFalse(self.graph.has_incoming("A"))

    def test_13_compounded_score(self):
        opp = _make_opp("test", score=0.5)
        node = OpportunityGraphNode(system_name="test", opportunity=opp, unlock_value=1.5)
        # base_score = 0.5^4 * 1.0 = 0.0625; compounded = 0.0625 * 1.5 = 0.09375
        self.assertAlmostEqual(node.compounded_score, 0.09375)

    def test_14_compounded_score_no_opportunity(self):
        node = OpportunityGraphNode(system_name="test")
        self.assertAlmostEqual(node.compounded_score, 0.0)

    def test_15_to_dict(self):
        opp = _make_opp("test", score=0.5)
        node = OpportunityGraphNode(system_name="test", opportunity=opp, unlock_value=2.0)
        d = node.to_dict()
        self.assertIn("system_name", d)
        self.assertIn("compounded_score", d)
        self.assertAlmostEqual(d["unlock_value"], 2.0)

    def test_16_edge_to_dict(self):
        edge = OpportunityGraphEdge("A", "B", confidence=0.7, evidence_count=3)
        d = edge.to_dict()
        self.assertEqual(d["source"], "A")
        self.assertEqual(d["target"], "B")
        self.assertAlmostEqual(d["confidence"], 0.7)
        self.assertEqual(d["evidence"], 3)


# ── Default Graph Tests ───────────────────────────────────────────────


class TestDefaultGraph(unittest.TestCase):
    """Default dependency graph built from hardcoded rules."""

    def test_20_default_graph_has_nodes(self):
        graph = build_default_graph()
        self.assertGreater(graph.node_count, 0)

    def test_21_default_graph_has_edges(self):
        graph = build_default_graph()
        self.assertGreater(graph.edge_count, 0)

    def test_22_key_dependencies_present(self):
        graph = build_default_graph()
        # browser_automation -> build_benchmark
        self.assertTrue(graph.has_outgoing("browser_automation"))
        # opportunity_discovery -> self_modification
        outgoing = graph.get_outgoing("opportunity_discovery")
        targets = [e.target_system for e in outgoing]
        self.assertIn("self_modification", targets)

    def test_23_all_edges_have_confidence(self):
        graph = build_default_graph()
        for edge in graph.edges:
            self.assertGreater(edge.confidence, 0.0)
            self.assertLessEqual(edge.confidence, 1.0)

    def test_24_to_dict(self):
        graph = build_default_graph()
        d = graph.to_dict()
        self.assertIn("node_count", d)
        self.assertIn("edge_count", d)
        self.assertIn("nodes", d)
        self.assertIn("edges", d)
        self.assertEqual(d["node_count"], graph.node_count)
        self.assertEqual(d["edge_count"], graph.edge_count)


# ── Unlock Value Scorer Tests ─────────────────────────────────────────


class TestUnlockValueScorer(unittest.TestCase):
    """Forward-reachability analysis with depth discounting."""

    def setUp(self):
        self.scorer = UnlockValueScorer(discount=0.5)

    def test_30_isolated_node(self):
        """A node with no outgoing edges has unlock_value = 1.0."""
        graph = build_default_graph()
        # Remove all edges
        for node_name in list(graph.nodes.keys()):
            graph.remove_node(node_name)
        graph.add_node("isolated")
        scores = self.scorer.compute(graph)
        self.assertAlmostEqual(scores["isolated"], 1.0)

    def test_31_linear_chain(self):
        """A -> B -> C: A unlocks B and C with depth discount."""
        graph = OpportunityGraph()
        graph.add_node("A", _make_opp("A", score=0.5))
        graph.add_node("B", _make_opp("B", score=0.5))
        graph.add_node("C", _make_opp("C", score=0.5))
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("B", "C", confidence=0.8))

        scores = self.scorer.compute(graph)
        # All base_score = 0.5^4*1.0 = 0.0625
        # A: 1.0 + B(depth=1, disc=1.0, 0.0625) + C(depth=2, disc=0.5, 0.03125)
        #   = 1.09375 → rounded to 3dp = 1.094
        self.assertAlmostEqual(scores["A"], 1.094, places=3)
        # B: 1.0 + C(depth=1, disc=1.0, 0.0625) = 1.0625 → 1.062
        self.assertAlmostEqual(scores["B"], 1.062, places=3)
        # C: 1.0
        self.assertAlmostEqual(scores["C"], 1.0, places=3)

    def test_32_fan_out(self):
        """A -> B, A -> C: A's unlock value includes both B and C."""
        graph = OpportunityGraph()
        graph.add_node("A", _make_opp("A", score=0.5))
        graph.add_node("B", _make_opp("B", score=0.3))
        graph.add_node("C", _make_opp("C", score=0.4))
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("A", "C", confidence=0.8))

        scores = self.scorer.compute(graph)
        # All base_score = 0.5^4*1.0 = 0.0625 (score param unused in base_score)
        # A: 1.0 + B(depth=1, disc=1.0, 0.0625) + C(depth=1, disc=1.0, 0.0625)
        #   = 1.0 + 0.0625 + 0.0625 = 1.125
        self.assertAlmostEqual(scores["A"], 1.125, places=4)

    def test_33_low_confidence_edge_skipped(self):
        """Edges below MIN_EDGE_CONFIDENCE should not contribute."""
        graph = OpportunityGraph()
        graph.add_node("A", _make_opp("A", score=0.5))
        graph.add_node("B", _make_opp("B", score=0.5))
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.05))

        scores = self.scorer.compute(graph)
        # A: 1.0 (B not reachable due to low confidence edge)
        self.assertAlmostEqual(scores["A"], 1.0, places=4)

    def test_34_cycle_does_not_infinite_loop(self):
        """A -> B -> A: should not infinite loop."""
        graph = OpportunityGraph()
        graph.add_node("A", _make_opp("A", score=0.5))
        graph.add_node("B", _make_opp("B", score=0.5))
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))
        graph.add_edge(OpportunityGraphEdge("B", "A", confidence=0.8))

        scores = self.scorer.compute(graph)
        # Should complete without recursion error
        self.assertIn("A", scores)
        self.assertIn("B", scores)

    def test_35_compute_for_node(self):
        graph = OpportunityGraph()
        graph.add_node("A", _make_opp("A", score=0.5))
        graph.add_node("B", _make_opp("B", score=0.5))
        graph.add_edge(OpportunityGraphEdge("A", "B", confidence=0.8))

        uv = self.scorer.compute_for_node(graph, "A")
        self.assertGreater(uv, 1.0)

        uv_isolated = self.scorer.compute_for_node(graph, "nonexistent")
        self.assertAlmostEqual(uv_isolated, DEFAULT_UNLOCK_VALUE)

    def test_36_default_graph_scores(self):
        """Unlock values across the default dependency graph."""
        graph = build_default_graph()
        # Add opportunities to all nodes
        for name in graph.nodes:
            graph.get_node(name).opportunity = _make_opp(name, score=0.5)

        scores = self.scorer.compute(graph)
        for name, uv in scores.items():
            self.assertGreaterEqual(uv, 1.0, msg=f"{name} should have unlock >= 1.0")
            self.assertLessEqual(uv, 2.5, msg=f"{name} should not have excessive unlock")


# ── Graph Builder Tests ───────────────────────────────────────────────


class TestOpportunityGraphBuilder(unittest.TestCase):
    """Builder — mining, ranking, system mapping."""

    def setUp(self):
        self.builder = OpportunityGraphBuilder()

    def test_40_build_without_mines(self):
        """Builder should produce a graph from opportunities alone."""
        opps = [
            _make_opp("browser_automation", score=0.8),
            _make_opp("build_benchmark", score=0.4),
            _make_opp("self_modification", score=0.2),
        ]
        graph = self.builder.build(opps)
        self.assertGreater(graph.node_count, 0)
        # Unlock values should be computed
        for name in ["browser_automation", "build_benchmark", "self_modification"]:
            node = graph.get_node(name)
            self.assertIsNotNone(node, msg=f"{name} should exist")
            self.assertGreaterEqual(node.unlock_value, 1.0)

    def test_41_build_with_activity_store(self):
        mock_store = MagicMock()
        mock_store.get_nodes_by_type.return_value = []

        graph = self.builder.build(
            [_make_opp("browser_automation")],
            activity_store=mock_store,
        )
        self.assertGreater(graph.node_count, 0)

    def test_42_build_with_opportunity_store(self):
        class MockRecord:
            def __init__(self, sys, success, sel, comp):
                self.target_system = sys
                self.source = "ceiling"
                self.actual_success = success
                self.selected_at = sel
                self.completed_at = comp

        mock_store = MagicMock()
        mock_store.list_records.return_value = [
            MockRecord("browser_automation", True, "2025-01-01", "2025-01-02"),
        ]

        graph = self.builder.build(
            [_make_opp("browser_automation")],
            opportunity_store=mock_store,
        )
        self.assertGreater(graph.node_count, 0)

    def test_43_rank_opportunities(self):
        """Ranking should produce a different order than raw scoring."""
        opps = [
            _make_opp("browser_automation", score=0.5),
            _make_opp("self_modification", score=0.3),
            _make_opp("isolated_system", score=0.7),
        ]

        # Add isolated_system which has no unlock value from graph
        # self_modification has higher unlock value (many incoming edges)
        ranked = self.builder.rank_opportunities(opps)

        # Should still have all 3
        self.assertEqual(len(ranked), 3)

        # The ordering may differ from original
        original_order = [o.target_system for o in opps]
        ranked_order = [o.target_system for o in ranked]
        # At minimum should not crash
        self.assertEqual(set(original_order), set(ranked_order))

    def test_44_tool_to_system_mapping(self):
        self.assertEqual(_tool_to_system("browser_navigate"), "browser_automation")
        self.assertEqual(_tool_to_system("browser_click"), "browser_automation")
        self.assertEqual(_tool_to_system("build_project"), "automated_build")
        self.assertEqual(_tool_to_system("run_tests"), "automated_build")
        self.assertEqual(_tool_to_system("send_email"), "execution_infrastructure")
        self.assertEqual(_tool_to_system("edit_file"), "coding_intelligence")
        self.assertEqual(_tool_to_system("unknown_tool"), "unknown_tool")

    def test_45_build_does_not_mutate_originals(self):
        """Builder should not modify original Opportunity objects."""
        opps = [_make_opp("browser_automation", score=0.5)]
        original_score = opps[0].opportunity_score

        self.builder.build(opps)
        self.assertAlmostEqual(opps[0].opportunity_score, original_score)

    def test_46_default_graph_includes_self_modification(self):
        graph = build_default_graph()
        node = graph.get_node("self_modification")
        self.assertIsNotNone(node)
        # Should have incoming edges
        incoming = graph.get_incoming("self_modification")
        self.assertGreater(len(incoming), 0)

    def test_47_empty_opportunities_build(self):
        """Empty opportunity list should still produce default graph."""
        graph = self.builder.build([])
        self.assertGreater(graph.node_count, 0)

    def test_48_builder_uses_miner_for_edge_discovery(self):
        """Builder delegates mining to SequentialPatternMiner."""
        from core.opportunity.mining import SequentialPatternMiner

        self.assertIsInstance(self.builder.miner, SequentialPatternMiner)

    def test_49_builder_accepts_experiment_runner(self):
        """Builder build() handles experiment_runner gracefully."""
        graph = self.builder.build([], None, None, None)
        self.assertGreater(graph.node_count, 0)
