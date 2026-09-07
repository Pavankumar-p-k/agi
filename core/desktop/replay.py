"""
Module: core.desktop.replay
Replay graph for recording and replaying desktop action sequences.
"""
from __future__ import annotations
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid
import logging

logger = logging.getLogger(__name__)


class NodeType(Enum):
    ACTION = "action"
    CONDITION = "condition"
    LOOP = "loop"
    PAUSE = "pause"
    START = "start"
    END = "end"


@dataclass
class ReplayNode:
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: str = ""
    node_type: NodeType = NodeType.ACTION
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    delay_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "node_type": self.node_type.value,
            "action": self.action,
            "params": self.params,
            "delay_ms": self.delay_ms,
            "metadata": self.metadata,
            "children": self.children,
        }


@dataclass
class ReplayEdge:
    source_id: str = ""
    target_id: str = ""
    condition: str = ""
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "condition": self.condition,
            "weight": self.weight,
        }


@dataclass
class ReplayGraph:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    nodes: list[ReplayNode] = field(default_factory=list)
    edges: list[ReplayEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    _recording: bool = False
    _record_buffer: list[ReplayNode] = field(default_factory=list)

    def record(self, action_name: str, params: dict[str, Any] | None = None, node_type: NodeType = NodeType.ACTION, delay_ms: int = 0, metadata: dict[str, Any] | None = None) -> ReplayNode:
        parent_id = self._record_buffer[-1].node_id if self._record_buffer else ""
        node = ReplayNode(
            node_type=node_type,
            action=action_name,
            params=params or {},
            delay_ms=delay_ms,
            metadata=metadata or {},
            parent_id=parent_id,
        )
        self.nodes.append(node)
        if self._record_buffer:
            last = self._record_buffer[-1]
            self.edges.append(ReplayEdge(source_id=last.node_id, target_id=node.node_id))
        self._record_buffer.append(node)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return node

    def add_node(self, node: ReplayNode) -> ReplayNode:
        self.nodes.append(node)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return node

    def remove_node(self, node_id: str) -> bool:
        before = len(self.nodes)
        self.nodes = [n for n in self.nodes if n.node_id != node_id]
        self.edges = [e for e in self.edges if e.source_id != node_id and e.target_id != node_id]
        if len(self.nodes) < before:
            self.updated_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def get_node(self, node_id: str) -> ReplayNode | None:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def add_edge(self, source_id: str, target_id: str, condition: str = "", weight: float = 1.0) -> ReplayEdge:
        edge = ReplayEdge(source_id=source_id, target_id=target_id, condition=condition, weight=weight)
        self.edges.append(edge)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return edge

    def start_recording(self) -> None:
        self._recording = True
        self._record_buffer.clear()
        logger.info("Replay recording started for graph '%s'", self.name)

    def stop_recording(self) -> list[ReplayNode]:
        self._recording = False
        recorded = list(self._record_buffer)
        self._record_buffer.clear()
        logger.info("Replay recording stopped, %d nodes captured", len(recorded))
        return recorded

    @property
    def is_recording(self) -> bool:
        return self._recording

    def node_list(self) -> list[ReplayNode]:
        return list(self.nodes)

    def clear(self) -> int:
        node_count = len(self.nodes)
        self.nodes.clear()
        self.edges.clear()
        self._record_buffer.clear()
        self._recording = False
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return node_count

    def to_dict(self) -> list[dict[str, Any]]:
        return [n.to_dict() for n in self.nodes]

    def topological_order(self) -> list[str]:
        node_ids = [n.node_id for n in self.nodes]
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        for edge in self.edges:
            if edge.target_id in in_degree:
                in_degree[edge.target_id] += 1
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        order = []
        while queue:
            nid = queue.pop(0)
            order.append(nid)
            for edge in self.edges:
                if edge.source_id == nid and edge.target_id in in_degree:
                    in_degree[edge.target_id] -= 1
                    if in_degree[edge.target_id] == 0:
                        queue.append(edge.target_id)
        return order


def desktop_replay(**kwargs: Any) -> ReplayGraph:
    return ReplayGraph(**kwargs)
