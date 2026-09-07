"""ActivityStore unit tests — CRUD, queries, edge cases."""

from datetime import datetime
import os
import tempfile
import unittest

from core.activity.models import ActivityEdge, ActivityNode, ActivityStatus
from core.activity.storage import ActivityStore


class TestActivityStore(unittest.TestCase):
    """SQLite-backed ActivityStore CRUD operations."""

    def setUp(self):
        self._tmp = tempfile.mktemp(suffix=".db")
        self.store = ActivityStore(db_path=self._tmp)

    def tearDown(self):
        # Use a robust retry for Windows handle release issues
        for _ in range(3):
            try:
                os.unlink(self._tmp)
                return
            except OSError:
                import time
                time.sleep(0.05)

    def _make_node(self, node_id="n1", activity_id="act_root",
                   node_type="goal", label="test", depth=0,
                   status=ActivityStatus.PENDING, **kw) -> ActivityNode:
        return ActivityNode(
            node_id=node_id, activity_id=activity_id,
            node_type=node_type, label=label, depth=depth,
            status=status, **kw,
        )

    # ── Node CRUD ───────────────────────────────────────────────────────────

    def test_01_create_node(self):
        node = self._make_node()
        saved = self.store.create_node(node)
        self.assertEqual(saved.node_id, "n1")
        self.assertIsNotNone(saved.created_at)

    def test_02_get_node(self):
        self.store.create_node(self._make_node())
        fetched = self.store.get_node("n1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.label, "test")
        self.assertEqual(fetched.node_type, "goal")

    def test_03_get_node_not_found(self):
        fetched = self.store.get_node("nonexistent")
        self.assertIsNone(fetched)

    def test_04_update_node(self):
        node = self._make_node()
        self.store.create_node(node)
        node.label = "updated"
        node.status = ActivityStatus.COMPLETED
        self.store.update_node(node)
        fetched = self.store.get_node("n1")
        self.assertEqual(fetched.label, "updated")
        self.assertEqual(fetched.status, ActivityStatus.COMPLETED)

    def test_05_delete_node(self):
        self.store.create_node(self._make_node("n1", node_type="goal"))
        self.store.create_node(self._make_node("n2", node_type="subgoal", parent_id="n1"))
        self.store.create_edge(ActivityEdge(
            edge_id="e1", from_node_id="n1", to_node_id="n2",
        ))
        self.store.delete_node("n1")
        self.assertIsNone(self.store.get_node("n1"))
        # Child node n2 still exists (no cascade)
        self.assertIsNotNone(self.store.get_node("n2"))
        # Edges referencing n1 are removed
        self.assertEqual(len(self.store.get_edges("n1")), 0)

    # ── Edge CRUD ───────────────────────────────────────────────────────────

    def test_06_create_edge(self):
        self.store.create_node(self._make_node("n1"))
        self.store.create_node(self._make_node("n2"))
        edge = ActivityEdge(edge_id="e1", from_node_id="n1", to_node_id="n2")
        saved = self.store.create_edge(edge)
        self.assertEqual(saved.edge_id, "e1")
        self.assertIsNotNone(saved.created_at)

    def test_07_get_edges(self):
        self.store.create_node(self._make_node("n1"))
        self.store.create_node(self._make_node("n2"))
        self.store.create_node(self._make_node("n3"))
        self.store.create_edge(ActivityEdge(edge_id="e1", from_node_id="n1", to_node_id="n2"))
        self.store.create_edge(ActivityEdge(edge_id="e2", from_node_id="n1", to_node_id="n3"))

        edges = self.store.get_edges("n1")
        self.assertEqual(len(edges), 2)

        incoming = self.store.get_incoming_edges("n2")
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0].from_node_id, "n1")

    def test_08_delete_edge(self):
        self.store.create_node(self._make_node("n1"))
        self.store.create_node(self._make_node("n2"))
        self.store.create_edge(ActivityEdge(edge_id="e1", from_node_id="n1", to_node_id="n2"))
        self.store.delete_edge("e1")
        self.assertEqual(len(self.store.get_edges("n1")), 0)

    # ── Queries ─────────────────────────────────────────────────────────────

    def test_09_get_activity_tree(self):
        self.store.create_node(self._make_node("root", depth=0, node_type="goal",
                                                activity_id="root"))
        self.store.create_node(self._make_node("c1", depth=1, node_type="subgoal",
                                                parent_id="root", activity_id="root"))
        self.store.create_node(self._make_node("c2", depth=1, node_type="subgoal",
                                                parent_id="root", activity_id="root"))
        self.store.create_node(self._make_node("gc1", depth=2, node_type="agent_call",
                                                parent_id="c1", activity_id="root"))

        tree = self.store.get_activity_tree("root")
        self.assertEqual(len(tree), 4)
        self.assertEqual([n.depth for n in tree], [0, 1, 1, 2])

    def test_10_get_timeline(self):
        self.store.create_node(self._make_node("a", node_type="goal", depth=0,
                                                activity_id="act"))
        self.store.create_node(self._make_node("b", node_type="agent_call", depth=1,
                                                activity_id="act", parent_id="a",
                                                started_at=datetime(2026, 1, 2)))
        self.store.create_node(self._make_node("c", node_type="tool_call", depth=2,
                                                activity_id="act", parent_id="b",
                                                started_at=datetime(2026, 1, 1)))
        timeline = self.store.get_activity_timeline("act")
        self.assertEqual(timeline[0].node_id, "c")
        self.assertEqual(timeline[1].node_id, "b")

    def test_11_get_active_activities(self):
        self.store.create_node(self._make_node("completed_root", depth=0,
                                                status=ActivityStatus.COMPLETED))
        self.store.create_node(self._make_node("active_root", depth=0,
                                                status=ActivityStatus.RUNNING))

        active = self.store.get_active_activities()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].node_id, "active_root")

    def test_12_get_incomplete_leaves(self):
        self.store.create_node(self._make_node("root", depth=0, activity_id="act"))
        self.store.create_node(self._make_node("c1", depth=1, activity_id="act",
                                                parent_id="root",
                                                status=ActivityStatus.COMPLETED))
        self.store.create_node(self._make_node("c2", depth=1, activity_id="act",
                                                parent_id="root",
                                                status=ActivityStatus.PENDING))

        leaves = self.store.get_incomplete_leaves("act")
        self.assertEqual(len(leaves), 1)
        self.assertEqual(leaves[0].node_id, "c2")

    def test_13_get_nodes_by_agent(self):
        self.store.create_node(self._make_node("n1", agent_id="forge",
                                                node_type="agent_call"))
        self.store.create_node(self._make_node("n2", agent_id="research",
                                                node_type="agent_call"))
        forge_nodes = self.store.get_nodes_by_agent("forge")
        self.assertEqual(len(forge_nodes), 1)
        self.assertEqual(forge_nodes[0].node_id, "n1")

    def test_14_get_nodes_by_type(self):
        self.store.create_node(self._make_node("n1", node_type="goal"))
        self.store.create_node(self._make_node("n2", node_type="agent_call"))
        self.store.create_node(self._make_node("n3", node_type="agent_call"))
        calls = self.store.get_nodes_by_type("agent_call")
        self.assertEqual(len(calls), 2)

    def test_15_count_by_status(self):
        self.store.create_node(self._make_node("n1", status=ActivityStatus.RUNNING,
                                                activity_id="act"))
        self.store.create_node(self._make_node("n2", status=ActivityStatus.COMPLETED,
                                                activity_id="act"))
        self.store.create_node(self._make_node("n3", status=ActivityStatus.COMPLETED,
                                                activity_id="act"))
        counts = self.store.count_by_status("act")
        self.assertEqual(counts.get("RUNNING"), 1)
        self.assertEqual(counts.get("COMPLETED"), 2)

    def test_16_search_nodes(self):
        self.store.create_node(self._make_node("n1", label="Research competitor apps"))
        self.store.create_node(self._make_node("n2", label="Build payment module"))
        self.store.create_node(self._make_node("n3", label="Email results"))
        results = self.store.search_nodes("payment")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].node_id, "n2")
        results2 = self.store.search_nodes("esearch")
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0].node_id, "n1")

    # ── Edge cases ──────────────────────────────────────────────────────────

    def test_17_duplicate_node_id_raises(self):
        self.store.create_node(self._make_node("dup"))
        with self.assertRaises(Exception):
            self.store.create_node(self._make_node("dup"))

    def test_18_full_artifact_chain(self):
        """Simulate a full activity chain: goal → agent → tool → artifact."""
        goal = self._make_node("g1", node_type="goal", label="Build app",
                                activity_id="g1")
        self.store.create_node(goal)
        sub = self._make_node("s1", node_type="subgoal", label="Research",
                               parent_id="g1", activity_id="g1", depth=1)
        self.store.create_node(sub)
        agent = self._make_node("a1", node_type="agent_call", label="Nexus",
                                 parent_id="s1", activity_id="g1",
                                 depth=2, agent_id="nexus")
        self.store.create_node(agent)
        art = self._make_node("art1", node_type="artifact", label="research_report",
                               activity_id="g1", depth=3,
                               parent_id="a1", origin_node_id="a1",
                               artifacts={"report": "art_001"})
        self.store.create_node(art)
        self.store.create_edge(ActivityEdge(
            edge_id="e1", from_node_id="a1", to_node_id="art1",
            edge_type="produces",
        ))
        tree = self.store.get_activity_tree("g1")
        self.assertEqual(len(tree), 4)
        self.assertEqual(tree[0].node_id, "g1")
        self.assertEqual(tree[3].node_id, "art1")
        edges = self.store.get_edges("a1")
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].edge_type, "produces")

    def test_19_persistence_across_store_instances(self):
        self.store.create_node(self._make_node("persist", label="survives restart"))
        store2 = ActivityStore(db_path=self._tmp)
        fetched = store2.get_node("persist")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.label, "survives restart")


if __name__ == "__main__":
    unittest.main()
