from __future__ import annotations

from collections import defaultdict
from typing import Any
from core.activity.models import ActivityEdge, ActivityNode, ActivityStatus


_DATABASES: dict[str, dict[str, Any]] = {}


class ActivityStore:
    def __init__(self, db_path: str = "activity.db", **_kwargs: Any):
        self.db_path = db_path
        self._data = _DATABASES.setdefault(db_path, {"nodes": {}, "edges": {}})

    def create_node(self, node: ActivityNode) -> ActivityNode:
        if node.node_id in self._data["nodes"]:
            raise ValueError(f"duplicate node id: {node.node_id}")
        self._data["nodes"][node.node_id] = node
        return node

    def get_node(self, node_id: str) -> ActivityNode | None:
        return self._data["nodes"].get(node_id)

    def update_node(self, node: ActivityNode) -> ActivityNode:
        self._data["nodes"][node.node_id] = node
        return node

    def delete_node(self, node_id: str) -> None:
        self._data["nodes"].pop(node_id, None)
        for edge_id, edge in list(self._data["edges"].items()):
            if node_id in (edge.from_node_id, edge.to_node_id):
                del self._data["edges"][edge_id]

    def create_edge(self, edge: ActivityEdge) -> ActivityEdge:
        self._data["edges"][edge.edge_id] = edge
        return edge

    def get_edges(self, node_id: str) -> list[ActivityEdge]:
        return [e for e in self._data["edges"].values() if node_id in (e.from_node_id, e.to_node_id)]

    def get_outgoing_edges(self, node_id: str) -> list[ActivityEdge]:
        return [e for e in self._data["edges"].values() if e.from_node_id == node_id]

    def get_incoming_edges(self, node_id: str) -> list[ActivityEdge]:
        return [e for e in self._data["edges"].values() if e.to_node_id == node_id]

    def delete_edge(self, edge_id: str) -> None:
        self._data["edges"].pop(edge_id, None)

    def _activity_nodes(self, activity_id: str) -> list[ActivityNode]:
        return [n for n in self._data["nodes"].values() if n.activity_id == activity_id]

    def get_activity_tree(self, activity_id: str) -> list[ActivityNode]:
        nodes = self._activity_nodes(activity_id)
        return sorted(nodes, key=lambda n: (n.depth, n.created_at))

    def get_activity_timeline(self, activity_id: str) -> list[ActivityNode]:
        return sorted(self._activity_nodes(activity_id), key=lambda n: n.depth, reverse=True)

    def get_active_activities(self) -> list[ActivityNode]:
        return [n for n in self._data["nodes"].values() if n.depth == 0 and n.status in {ActivityStatus.RUNNING, ActivityStatus.PENDING, ActivityStatus.SUSPENDED}]

    def get_incomplete_leaves(self, activity_id: str) -> list[ActivityNode]:
        nodes = self._activity_nodes(activity_id)
        active = {ActivityStatus.PENDING, ActivityStatus.RUNNING, ActivityStatus.SUSPENDED}
        return [
            node for node in nodes
            if node.depth > 0
            and node.status in active
            and not any(child.parent_id == node.node_id and child.status in active for child in nodes)
        ]

    def get_nodes_by_agent(self, agent_id: str) -> list[ActivityNode]:
        return [n for n in self._data["nodes"].values() if n.agent_id == agent_id]

    def get_nodes_by_type(self, node_type: str) -> list[ActivityNode]:
        return [n for n in self._data["nodes"].values() if n.node_type == node_type]

    def count_by_status(self, activity_id: str) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for node in self._activity_nodes(activity_id):
            counts[node.status.value] += 1
        return dict(counts)

    def search_nodes(self, query: str) -> list[ActivityNode]:
        q = query.casefold()
        return [n for n in self._data["nodes"].values() if q in n.label.casefold()]
