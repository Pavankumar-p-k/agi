"""ReplayGraph — append-only DAG of desktop actions (Gate 6).

Every accepted action becomes a ReplayNode chained to its predecessor,
so a session can be audited or replayed deterministically.
"""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReplayNode:
    node_id: str
    action: str
    params: dict = field(default_factory=dict)
    parent_id: Optional[str] = None
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "action": self.action,
            "params": dict(self.params),
            "parent_id": self.parent_id,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


class ReplayGraph:
    """Thread-safe append-only chain of desktop actions."""

    def __init__(self) -> None:
        self.nodes: list[ReplayNode] = []
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    def record(self, action: str, params: Optional[dict] = None) -> ReplayNode:
        with self._lock:
            parent_id = self.nodes[-1].node_id if self.nodes else None
            node = ReplayNode(
                node_id=f"act_{next(self._counter)}",
                action=action,
                params=dict(params or {}),
                parent_id=parent_id,
                timestamp=0.0,
            )
            self.nodes.append(node)
            return node

    def to_dict(self) -> list:
        with self._lock:
            return [n.to_dict() for n in self.nodes]

    def clear(self) -> None:
        with self._lock:
            self.nodes.clear()

    def last(self) -> Optional[ReplayNode]:
        with self._lock:
            return self.nodes[-1] if self.nodes else None

    def __len__(self) -> int:
        return len(self.nodes)


# Module-level singleton.
desktop_replay = ReplayGraph()


__all__ = ["ReplayNode", "ReplayGraph", "desktop_replay"]
