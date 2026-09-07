"""
Module: core.capability.graph
Capability graph node model.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class CapabilityNode:
    capability_id: str = ""
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "metadata": self.metadata,
        }


class CapabilityGraph:
    def __init__(self):
        self._nodes: dict[str, CapabilityNode] = {}

    def add_node(self, node: CapabilityNode) -> CapabilityNode:
        self._nodes[node.capability_id] = node
        return node

    def get_node(self, capability_id: str) -> CapabilityNode | None:
        return self._nodes.get(capability_id)

    def nodes(self) -> list[CapabilityNode]:
        return list(self._nodes.values())


def capability_graph(**kwargs: Any) -> CapabilityGraph:
    return CapabilityGraph(**kwargs)
