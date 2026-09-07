"""Sequential Pattern Miner tests — Phase 20.

Covers:
  - MinedEdge models and serialization
  - PromotionRules gates
  - Confidence and lift computation
  - ActivityGraph mining (mocked store)
  - OpportunityStore mining (mocked store)
  - Experiment mining (mocked runner)
  - mine_all deduplication
  - get_promotable_edges filtering
  - merge_with_defaults strategy
  - EdgeSource enum
"""

import unittest
from unittest.mock import MagicMock

from core.opportunity.mining import (
    MIN_CONFIDENCE,
    MIN_LIFT,
    MIN_SUPPORT,
    EdgeSource,
    MinedEdge,
    PromotionRules,
    SequentialPatternMiner,
    _tool_to_system,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _make_mock_node(label: str, status: str = "COMPLETED",
                    activity_id: str = "act_1",
                    completed_at: str = "2025-01-01T00:00:00",
                    created_at: str = "2025-01-01T00:00:00") -> MagicMock:
    node = MagicMock()
    node.label = label
    node.status = status
    node.activity_id = activity_id
    node.completed_at = completed_at
    node.created_at = created_at
    return node


def _make_mock_record(target_system: str, success: bool = True,
                      selected_at: str = "2025-01-02T00:00:00",
                      completed_at: str = "2025-01-01T00:00:00") -> MagicMock:
    rec = MagicMock()
    rec.target_system = target_system
    rec.actual_success = success
    rec.selected_at = selected_at
    rec.completed_at = completed_at
    return rec


def _make_mock_experiment(status: str = "completed",
                          knob_name: str = "test_knob",
                          created_at: str = "2025-01-01T00:00:00") -> MagicMock:
    exp = MagicMock()
    exp.status = status
    exp.created_at = created_at
    exp.started_at = created_at
    change = MagicMock()
    change.knob_name = knob_name
    exp.knob_changes = [change]
    return exp


# ── MinedEdge Model Tests ─────────────────────────────────────────────


class TestMinedEdge(unittest.TestCase):

    def test_01_default_values(self):
        e = MinedEdge(source_system="A", target_system="B")
        self.assertEqual(e.source_system, "A")
        self.assertEqual(e.target_system, "B")
        self.assertEqual(e.support, 0)
        self.assertAlmostEqual(e.confidence, 0.0)
        self.assertAlmostEqual(e.lift, 1.0)

    def test_02_to_dict(self):
        e = MinedEdge("A", "B", support=5, confidence=0.8, lift=1.5,
                      total_observations=100)
        d = e.to_dict()
        self.assertEqual(d["source"], "A")
        self.assertEqual(d["target"], "B")
        self.assertEqual(d["support"], 5)

    def test_03_to_dict_rounding(self):
        e = MinedEdge("A", "B", confidence=0.876543, lift=1.234567)
        d = e.to_dict()
        self.assertAlmostEqual(d["confidence"], 0.877)
        self.assertAlmostEqual(d["lift"], 1.235)

    def test_04_equality_by_value(self):
        e1 = MinedEdge("A", "B", support=3)
        e2 = MinedEdge("A", "B", support=5)
        # Not same object — use tuple key
        self.assertEqual(
            (e1.source_system, e1.target_system),
            (e2.source_system, e2.target_system),
        )


# ── PromotionRules Tests ──────────────────────────────────────────────


class TestPromotionRules(unittest.TestCase):

    def setUp(self):
        self.rules = PromotionRules()

    def test_10_default_thresholds(self):
        self.assertEqual(self.rules.min_support, MIN_SUPPORT)
        self.assertAlmostEqual(self.rules.min_confidence, MIN_CONFIDENCE)
        self.assertAlmostEqual(self.rules.min_lift, MIN_LIFT)

    def test_11_promotable_passes(self):
        edge = MinedEdge("A", "B", support=10, confidence=0.8, lift=2.0)
        self.assertTrue(self.rules.is_promotable(edge))

    def test_12_low_support_fails(self):
        edge = MinedEdge("A", "B", support=1, confidence=0.9, lift=3.0)
        self.assertFalse(self.rules.is_promotable(edge))

    def test_13_low_confidence_fails(self):
        edge = MinedEdge("A", "B", support=10, confidence=0.3, lift=2.0)
        self.assertFalse(self.rules.is_promotable(edge))

    def test_14_low_lift_fails(self):
        edge = MinedEdge("A", "B", support=10, confidence=0.8, lift=1.0)
        self.assertFalse(self.rules.is_promotable(edge))

    def test_15_custom_thresholds(self):
        strict = PromotionRules(min_support=2, min_confidence=0.5, min_lift=1.0)
        edge = MinedEdge("A", "B", support=3, confidence=0.55, lift=1.1)
        self.assertTrue(strict.is_promotable(edge))

    def test_16_exactly_at_threshold(self):
        edge = MinedEdge(
            "A", "B",
            support=MIN_SUPPORT,
            confidence=MIN_CONFIDENCE,
            lift=MIN_LIFT,
        )
        self.assertTrue(self.rules.is_promotable(edge))

    def test_17_just_below_threshold(self):
        edge = MinedEdge(
            "A", "B",
            support=MIN_SUPPORT - 1,
            confidence=MIN_CONFIDENCE,
            lift=MIN_LIFT,
        )
        self.assertFalse(self.rules.is_promotable(edge))


# ── Statistics Tests ──────────────────────────────────────────────────


class TestStatistics(unittest.TestCase):

    def test_20_confidence_basic(self):
        c = SequentialPatternMiner.compute_confidence(5, 10)
        self.assertAlmostEqual(c, 0.5)

    def test_21_confidence_zero_denominator(self):
        c = SequentialPatternMiner.compute_confidence(0, 0)
        self.assertAlmostEqual(c, 0.0)

    def test_22_confidence_perfect(self):
        c = SequentialPatternMiner.compute_confidence(10, 10)
        self.assertAlmostEqual(c, 1.0)

    def test_23_lift_basic(self):
        # P(B|A) = 0.8, P(B) = 0.4, lift = 2.0
        l = SequentialPatternMiner.compute_lift(0.8, count_b=40, total=100)
        self.assertAlmostEqual(l, 2.0)

    def test_24_lift_zero_prob_b(self):
        l = SequentialPatternMiner.compute_lift(0.8, count_b=0, total=100)
        self.assertAlmostEqual(l, 1.0)

    def test_25_lift_zero_total(self):
        l = SequentialPatternMiner.compute_lift(0.8, count_b=10, total=0)
        self.assertAlmostEqual(l, 1.0)

    def test_26_lift_neutral(self):
        # P(B|A) == P(B) => lift = 1.0
        l = SequentialPatternMiner.compute_lift(0.5, count_b=50, total=100)
        self.assertAlmostEqual(l, 1.0)


# ── Tool-to-System Mapping Tests ─────────────────────────────────────


class TestToolToSystem(unittest.TestCase):

    def test_30_browser_mapping(self):
        self.assertEqual(_tool_to_system("browser_navigate"), "browser_automation")
        self.assertEqual(_tool_to_system("browser_click"), "browser_automation")
        self.assertEqual(_tool_to_system("browser_snapshot"), "browser_automation")

    def test_31_build_mapping(self):
        self.assertEqual(_tool_to_system("build_project"), "automated_build")
        self.assertEqual(_tool_to_system("run_tests"), "automated_build")

    def test_32_email_mapping(self):
        self.assertEqual(_tool_to_system("send_email"), "execution_infrastructure")

    def test_33_unknown_tool(self):
        result = _tool_to_system("some_unknown_tool")
        self.assertEqual(result, "some_unknown_tool")

    def test_34_browser_prefix_catch_all(self):
        self.assertEqual(_tool_to_system("browser_scroll_down"), "browser_automation")


# ── Mining Tests ──────────────────────────────────────────────────────


class TestMineActivityGraph(unittest.TestCase):

    def setUp(self):
        self.miner = SequentialPatternMiner()

    def test_40_empty_store_returns_empty(self):
        store = MagicMock()
        store.get_nodes_by_type.return_value = []
        edges = self.miner.mine_activity_graph(store)
        self.assertEqual(edges, [])

    def test_41_single_activity_two_tools(self):
        store = MagicMock()
        store.get_nodes_by_type.return_value = [
            _make_mock_node("browser_navigate", completed_at="2025-01-01T00:01:00"),
            _make_mock_node("build_project", completed_at="2025-01-01T00:02:00"),
        ]
        edges = self.miner.mine_activity_graph(store)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].source_system, "browser_automation")
        self.assertEqual(edges[0].target_system, "automated_build")

    def test_42_different_systems_paired(self):
        store = MagicMock()
        store.get_nodes_by_type.return_value = [
            _make_mock_node("browser_navigate", completed_at="2025-01-01T00:01:00"),
            _make_mock_node("build_project", completed_at="2025-01-01T00:02:00"),
        ]
        edges = self.miner.mine_activity_graph(store)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].source_system, "browser_automation")
        self.assertEqual(edges[0].target_system, "automated_build")

    def test_43_self_loops_skipped(self):
        store = MagicMock()
        store.get_nodes_by_type.return_value = [
            _make_mock_node("build_project", completed_at="2025-01-01T00:01:00"),
            _make_mock_node("build_project", completed_at="2025-01-01T00:02:00"),
        ]
        edges = self.miner.mine_activity_graph(store)
        # Same system = self-loop, skipped
        self.assertEqual(len(edges), 0)

    def test_44_multiple_activities(self):
        store = MagicMock()
        store.get_nodes_by_type.return_value = [
            _make_mock_node("browser_navigate", activity_id="a1",
                            completed_at="2025-01-01T00:01:00"),
            _make_mock_node("build_project", activity_id="a1",
                            completed_at="2025-01-01T00:02:00"),
            _make_mock_node("run_tests", activity_id="a2",
                            completed_at="2025-01-01T00:03:00"),
            _make_mock_node("send_email", activity_id="a2",
                            completed_at="2025-01-01T00:04:00"),
        ]
        edges = self.miner.mine_activity_graph(store)
        self.assertEqual(len(edges), 2)

    def test_45_incomplete_nodes_skipped(self):
        store = MagicMock()
        store.get_nodes_by_type.return_value = [
            _make_mock_node("build_project", status="FAILED"),
            _make_mock_node("run_tests", status="COMPLETED"),
        ]
        edges = self.miner.mine_activity_graph(store)
        self.assertEqual(len(edges), 0)

    def test_46_store_exception_handled(self):
        store = MagicMock()
        store.get_nodes_by_type.side_effect = ValueError("DB error")
        edges = self.miner.mine_activity_graph(store)
        self.assertEqual(edges, [])


class TestMineOpportunityStore(unittest.TestCase):

    def setUp(self):
        self.miner = SequentialPatternMiner()

    def test_50_empty_store_returns_empty(self):
        store = MagicMock()
        store.list_records.return_value = []
        edges = self.miner.mine_opportunity_store(store)
        self.assertEqual(edges, [])

    def test_51_two_completed_opportunities(self):
        store = MagicMock()
        store.list_records.return_value = [
            _make_mock_record("browser_automation",
                              completed_at="2025-01-01", selected_at="2025-01-01"),
            _make_mock_record("automated_build",
                              completed_at="2025-01-03", selected_at="2025-01-02"),
        ]
        edges = self.miner.mine_opportunity_store(store)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].source_system, "browser_automation")
        self.assertEqual(edges[0].target_system, "automated_build")

    def test_52_chronological_order(self):
        """B selected after A completed → edge."""
        store = MagicMock()
        store.list_records.return_value = [
            _make_mock_record("A", completed_at="2025-01-01", selected_at="2025-01-01"),
            _make_mock_record("B", completed_at="2025-01-03", selected_at="2025-01-02"),
            _make_mock_record("C", completed_at="2025-01-05", selected_at="2025-01-04"),
        ]
        edges = self.miner.mine_opportunity_store(store)
        self.assertGreater(len(edges), 0)

    def test_53_self_loops_skipped(self):
        store = MagicMock()
        store.list_records.return_value = [
            _make_mock_record("A", completed_at="2025-01-01", selected_at="2025-01-01"),
            _make_mock_record("A", completed_at="2025-01-03", selected_at="2025-01-02"),
        ]
        edges = self.miner.mine_opportunity_store(store)
        self.assertEqual(len(edges), 0)

    def test_54_exception_handled(self):
        store = MagicMock()
        store.list_records.side_effect = RuntimeError("fail")
        edges = self.miner.mine_opportunity_store(store)
        self.assertEqual(edges, [])


class TestMineExperiments(unittest.TestCase):

    def setUp(self):
        self.miner = SequentialPatternMiner()

    def test_60_empty_returns_empty(self):
        runner = MagicMock()
        runner.get_experiments.return_value = []
        edges = self.miner.mine_experiments(runner)
        self.assertEqual(edges, [])

    def test_61_two_adjacent_experiments(self):
        runner = MagicMock()
        runner.get_experiments.return_value = [
            _make_mock_experiment(knob_name="system_A",
                                  created_at="2025-01-01"),
            _make_mock_experiment(knob_name="system_B",
                                  created_at="2025-01-02"),
        ]
        edges = self.miner.mine_experiments(runner)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].source_system, "system_A")
        self.assertEqual(edges[0].target_system, "system_B")

    def test_62_failed_experiment_excluded(self):
        runner = MagicMock()
        runner.get_experiments.return_value = [
            _make_mock_experiment(status="failed", knob_name="system_A",
                                  created_at="2025-01-01"),
            _make_mock_experiment(knob_name="system_B",
                                  created_at="2025-01-02"),
        ]
        edges = self.miner.mine_experiments(runner)
        self.assertEqual(len(edges), 0)

    def test_63_exception_handled(self):
        runner = MagicMock()
        runner.get_experiments.side_effect = ConnectionError("no db")
        edges = self.miner.mine_experiments(runner)
        self.assertEqual(edges, [])


# ── mine_all Deduplication Tests ──────────────────────────────────────


class TestMineAll(unittest.TestCase):

    def setUp(self):
        self.miner = SequentialPatternMiner()

    def test_70_no_sources_returns_empty(self):
        edges = self.miner.mine_all()
        self.assertEqual(edges, [])

    def test_71_deduplicates_across_sources(self):
        store = MagicMock()
        store.get_nodes_by_type.return_value = [
            _make_mock_node("build_project", completed_at="2025-01-01T00:01:00"),
            _make_mock_node("browser_navigate", completed_at="2025-01-01T00:02:00"),
        ]
        edges = self.miner.mine_all(activity_store=store)
        # build_project → browser_navigate: automated_build → browser_automation
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].source_system, "automated_build")


# ── get_promotable_edges Tests ────────────────────────────────────────


class TestGetPromotableEdges(unittest.TestCase):

    def setUp(self):
        self.miner = SequentialPatternMiner()

    def test_80_all_promotable(self):
        edges = [
            MinedEdge("A", "B", support=10, confidence=0.8, lift=2.0),
            MinedEdge("C", "D", support=8, confidence=0.7, lift=1.5),
        ]
        promo = self.miner.get_promotable_edges(edges)
        self.assertEqual(len(promo), 2)

    def test_81_none_promotable(self):
        edges = [
            MinedEdge("A", "B", support=1, confidence=0.3, lift=1.0),
        ]
        promo = self.miner.get_promotable_edges(edges)
        self.assertEqual(len(promo), 0)

    def test_82_mixed_promotable(self):
        edges = [
            MinedEdge("A", "B", support=10, confidence=0.8, lift=2.0),
            MinedEdge("C", "D", support=2, confidence=0.9, lift=3.0),
        ]
        promo = self.miner.get_promotable_edges(edges)
        self.assertEqual(len(promo), 1)
        self.assertEqual(promo[0].source_system, "A")


# ── Merge Tests ───────────────────────────────────────────────────────


class TestMergeWithDefaults(unittest.TestCase):

    def setUp(self):
        self.miner = SequentialPatternMiner()

    def test_90_no_learned_returns_defaults(self):
        from core.opportunity.graph import build_default_graph

        default = build_default_graph()
        merged = self.miner.merge_with_defaults([], default)
        self.assertEqual(len(merged), default.edge_count)

    def test_91_learned_replaces_default_when_higher_confidence(self):
        from core.opportunity.graph import (
            OpportunityGraph,
            OpportunityGraphEdge,
            build_default_graph,
        )

        # Default: browser_automation → build_benchmark with conf=0.50
        # Learned: same edge with conf=0.85 → should merge
        learned = [
            MinedEdge("browser_automation", "build_benchmark",
                      support=20, confidence=0.85, lift=2.5),
        ]
        merged = self.miner.merge_with_defaults(learned)

        edge = next(e for e in merged
                    if e.source_system == "browser_automation"
                    and e.target_system == "build_benchmark")
        self.assertEqual(edge.source_type, EdgeSource.MERGED.value)
        self.assertAlmostEqual(edge.confidence, 0.85)
        self.assertEqual(edge.support_count, 20)
        self.assertAlmostEqual(edge.lift, 2.5)

    def test_92_learned_not_replaces_when_lower_confidence(self):
        learned = [
            MinedEdge("browser_automation", "build_benchmark",
                      support=5, confidence=0.30, lift=0.8),
        ]
        merged = self.miner.merge_with_defaults(learned)
        edge = next(e for e in merged
                    if e.source_system == "browser_automation"
                    and e.target_system == "build_benchmark")
        self.assertEqual(edge.source_type, "default")
        self.assertAlmostEqual(edge.confidence, 0.50)

    def test_93_learned_novel_edge_added_when_promotable(self):
        learned = [
            MinedEdge("novel_system", "browser_automation",
                      support=10, confidence=0.8, lift=2.0),
        ]
        merged = self.miner.merge_with_defaults(learned)
        edge = next((e for e in merged
                     if e.source_system == "novel_system"
                     and e.target_system == "browser_automation"), None)
        self.assertIsNotNone(edge)
        self.assertEqual(edge.source_type, EdgeSource.LEARNED.value)
        self.assertAlmostEqual(edge.confidence, 0.8)

    def test_94_learned_novel_edge_skipped_when_not_promotable(self):
        learned = [
            MinedEdge("novel_system", "browser_automation",
                      support=1, confidence=0.3, lift=1.0),
        ]
        merged = self.miner.merge_with_defaults(learned)
        edge = next((e for e in merged
                     if e.source_system == "novel_system"), None)
        self.assertIsNone(edge)

    def test_95_default_not_removed_by_novel_edge(self):
        before = len(self.miner.merge_with_defaults([]))
        learned = [
            MinedEdge("novel", "other", support=10, confidence=0.8, lift=2.0),
        ]
        after = len(self.miner.merge_with_defaults(learned))
        self.assertGreater(after, before)

    def test_96_merge_without_default_graph_argument(self):
        learned = [
            MinedEdge("novel", "other", support=10, confidence=0.8, lift=2.0),
        ]
        merged = self.miner.merge_with_defaults(learned)
        # Should build defaults internally
        self.assertGreater(len(merged), 0)


# ── EdgeSource Enum Tests ─────────────────────────────────────────────


class TestEdgeSource(unittest.TestCase):

    def test_100_values(self):
        self.assertEqual(EdgeSource.DEFAULT.value, "default")
        self.assertEqual(EdgeSource.LEARNED.value, "learned")
        self.assertEqual(EdgeSource.MERGED.value, "merged")

    def test_101_string_comparison(self):
        self.assertEqual("default", EdgeSource.DEFAULT.value)
        self.assertEqual("learned", EdgeSource.LEARNED)
