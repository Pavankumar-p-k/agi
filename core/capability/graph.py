from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from core.capability.models import Capability
from core.capability.registry import capability_registry


@dataclass(frozen=True)
class CapabilityNode:
    capability_id: str
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityEdge:
    from_id: str
    to_id: str
    edge_type: str = "depends_on"


@dataclass(frozen=True)
class CapabilitySubgraph:
    goal: str
    nodes: tuple[CapabilityNode, ...]
    edges: tuple[CapabilityEdge, ...]
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            raw = json.dumps({
                "goal": self.goal,
                "nodes": [(n.capability_id, n.version) for n in self.nodes],
                "edges": [(e.from_id, e.to_id, e.edge_type) for e in self.edges],
            }, sort_keys=True)
            object.__setattr__(self, "fingerprint", hashlib.sha256(raw.encode()).hexdigest()[:16])


_GOAL_TEMPLATES: dict[str, tuple[list[dict], list[dict]]] = {
    "build": (
        [
            {"id": "coding", "version": 1},
            {"id": "testing", "version": 1},
            {"id": "deployment", "version": 1},
        ],
        [
            {"from": "coding", "to": "testing", "type": "depends_on"},
            {"from": "testing", "to": "deployment", "type": "depends_on"},
        ],
    ),
    "research": (
        [
            {"id": "research", "version": 1},
            {"id": "documentation", "version": 1},
        ],
        [
            {"from": "research", "to": "documentation", "type": "depends_on"},
        ],
    ),
    "publish": (
        [
            {"id": "coding", "version": 1},
            {"id": "testing", "version": 1},
            {"id": "deployment", "version": 1},
            {"id": "email", "version": 1},
        ],
        [
            {"from": "coding", "to": "testing", "type": "depends_on"},
            {"from": "testing", "to": "deployment", "type": "depends_on"},
            {"from": "deployment", "to": "email", "type": "depends_on"},
        ],
    ),
    "browse": (
        [
            {"id": "research", "version": 1},
            {"id": "browser", "version": 1},
        ],
        [
            {"from": "research", "to": "browser", "type": "depends_on"},
        ],
    ),
}


class CapabilityGraph:
    def __init__(self) -> None:
        self._cache: dict[str, CapabilitySubgraph] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def resolve_goal(self, goal: str) -> CapabilitySubgraph:
        goal_lower = goal.lower()
        cache_key = hashlib.sha256(goal_lower.encode()).hexdigest()

        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        self._cache_misses += 1

        # Check goal templates first
        for keyword, (node_defs, edge_defs) in _GOAL_TEMPLATES.items():
            if keyword in goal_lower:
                nodes = tuple(
                    CapabilityNode(capability_id=nd["id"], version=nd["version"])
                    for nd in node_defs
                )
                edges = tuple(
                    CapabilityEdge(from_id=ed["from"], to_id=ed["to"], edge_type=ed["type"])
                    for ed in edge_defs
                )
                subgraph = CapabilitySubgraph(goal=goal, nodes=nodes, edges=edges)
                self._cache[cache_key] = subgraph
                return subgraph

        # Fall back to registry matching
        matched = capability_registry.match_goal(goal_lower)
        if not matched:
            empty = CapabilitySubgraph(goal=goal, nodes=(), edges=())
            self._cache[cache_key] = empty
            return empty

        # Build dependency edges between matched capabilities
        nodes: list[CapabilityNode] = []
        edges: list[CapabilityEdge] = []
        for cap in matched:
            nodes.append(CapabilityNode(capability_id=cap.id, version=cap.version))

        # Add compatibility edges
        matched_set = {c.id: c for c in matched}
        for i, cap_a in enumerate(matched):
            for cap_b in list(matched)[i + 1:]:
                if cap_a.compatible_with(cap_b):
                    edges.append(CapabilityEdge(
                        from_id=cap_a.id, to_id=cap_b.id, edge_type="depends_on",
                    ))

        subgraph = CapabilitySubgraph(goal=goal, nodes=tuple(nodes), edges=tuple(edges))
        self._cache[cache_key] = subgraph
        return subgraph

    def invalidate(self, goal: str | None = None) -> None:
        if goal:
            goal_lower = goal.lower()
            cache_key = hashlib.sha256(goal_lower.encode()).hexdigest()
            self._cache.pop(cache_key, None)
        else:
            self._cache.clear()

    def cache_stats(self) -> dict:
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": round(hit_rate, 3),
            "cached_subgraphs": len(self._cache),
        }

    @property
    def fingerprints(self) -> dict[str, str]:
        return {k: v.fingerprint for k, v in self._cache.items()}


capability_graph = CapabilityGraph()
