from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


MAX_ESTIMATE_SECONDS = 86400  # 24h cap on single-node estimates


class ExecutionNode:
    """A single node in the execution graph.

    Represents one step of work: planning, research, coding,
    testing, etc. Every node is independently editable.
    """

    def __init__(
        self,
        label: str,
        node_type: str = "task",
        parent_id: str | None = None,
        status: str = "pending",
        confidence: float = 0.0,
        estimate_seconds: int | None = None,
        detail: str = "",
        trust_level: str = "safe",
        can_skip: bool = True,
        can_reorder: bool = True,
        node_id: str | None = None,
    ) -> None:
        self.node_id = node_id or f"n_{uuid.uuid4().hex[:10]}"
        self.parent_id = parent_id
        self.label = label
        self.node_type = node_type
        self.status = status
        self.confidence = confidence
        self.estimate_seconds = min(estimate_seconds, MAX_ESTIMATE_SECONDS) if estimate_seconds else None
        self.elapsed_seconds: int | None = None
        self.detail = detail
        self.trust_level = trust_level
        self.can_skip = can_skip
        self.can_reorder = can_reorder
        self.files: list[str] = []
        self.artifacts: list[str] = []
        self.logs: list[str] = []
        self.agent_reasoning: str | None = None
        self.error: str | None = None
        self.children: list[ExecutionNode] = []
        self.created_at = datetime.utcnow().isoformat()
        self.started_at: str | None = None
        self.completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "label": self.label,
            "node_type": self.node_type,
            "status": self.status,
            "confidence": self.confidence,
            "estimate_seconds": self.estimate_seconds,
            "elapsed_seconds": self.elapsed_seconds,
            "detail": self.detail,
            "trust_level": self.trust_level,
            "can_skip": self.can_skip,
            "can_reorder": self.can_reorder,
            "files": self.files,
            "artifacts": self.artifacts,
            "logs": self.logs,
            "agent_reasoning": self.agent_reasoning,
            "error": self.error,
            "children": [c.to_dict() for c in self.children],
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    def add_child(self, node: ExecutionNode) -> ExecutionNode:
        node.parent_id = self.node_id
        self.children.append(node)
        return node

    def total_estimate_seconds(self) -> int | None:
        total = 0
        if self.estimate_seconds:
            total += self.estimate_seconds
        for c in self.children:
            child_est = c.total_estimate_seconds()
            if child_est:
                total += child_est
        return total if total > 0 else None


class ExecutionGraph:
    """Tree of execution nodes for one user goal.

    The graph IS the execution plan. Every node can be paused,
    retried, removed, inserted, or reordered at runtime.
    """

    def __init__(self, goal: str, goal_id: str | None = None) -> None:
        self.goal = goal
        self.goal_id = goal_id or f"g_{uuid.uuid4().hex[:10]}"
        self.status: str = "active"
        self.created_at = datetime.utcnow().isoformat()
        self._nodes: dict[str, ExecutionNode] = {}
        self._root: ExecutionNode | None = None

    @property
    def root(self) -> ExecutionNode | None:
        return self._root

    def set_root(self, node: ExecutionNode) -> None:
        self._root = node
        self._index_node(node)

    def add_node(
        self,
        parent_id: str | None,
        label: str,
        node_type: str = "task",
        **kwargs: Any,
    ) -> ExecutionNode:
        node = ExecutionNode(
            label=label,
            node_type=node_type,
            parent_id=parent_id,
            **kwargs,
        )
        if parent_id and parent_id in self._nodes:
            self._nodes[parent_id].add_child(node)
        elif self._root is None:
            self._root = node
        self._index_node(node)
        return node

    def insert_after(self, after_id: str, label: str, **kwargs: Any) -> ExecutionNode:
        after = self._nodes.get(after_id)
        if not after:
            raise ValueError(f"Node {after_id} not found")
        node = ExecutionNode(label=label, parent_id=after.parent_id, **kwargs)
        parent = self._nodes.get(after.parent_id) if after.parent_id else self._root
        if parent:
            idx = next(
                (i for i, c in enumerate(parent.children) if c.node_id == after_id),
                -1,
            )
            parent.children.insert(idx + 1, node)
        self._index_node(node)
        return node

    def remove_node(self, node_id: str) -> bool:
        node = self._nodes.pop(node_id, None)
        if not node:
            return False
        parent = self._nodes.get(node.parent_id) if node.parent_id else self._root
        if parent:
            parent.children = [c for c in parent.children if c.node_id != node_id]
        elif self._root and self._root.node_id == node_id:
            self._root = None
        for child_id in list(self._nodes.keys()):
            n = self._nodes.get(child_id)
            if n and n.parent_id == node_id:
                self._nodes.pop(child_id, None)
        return True

    def reorder_child(self, parent_id: str, node_id: str, new_index: int) -> bool:
        parent = self._nodes.get(parent_id) if parent_id else self._root
        if not parent:
            return False
        idx = next(
            (i for i, c in enumerate(parent.children) if c.node_id == node_id),
            -1,
        )
        if idx == -1:
            return False
        node = parent.children.pop(idx)
        new_index = max(0, min(new_index, len(parent.children)))
        parent.children.insert(new_index, node)
        return True

    def get_node(self, node_id: str) -> ExecutionNode | None:
        return self._nodes.get(node_id)

    def update_node(self, node_id: str, **updates: Any) -> ExecutionNode | None:
        node = self._nodes.get(node_id)
        if not node:
            return None
        for key, value in updates.items():
            if hasattr(node, key):
                setattr(node, key, value)
        return node

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "goal_id": self.goal_id,
            "status": self.status,
            "created_at": self.created_at,
            "root": self._root.to_dict() if self._root else None,
        }

    def _index_node(self, node: ExecutionNode) -> None:
        self._nodes[node.node_id] = node
        for child in node.children:
            self._index_node(child)
