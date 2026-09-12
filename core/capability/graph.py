"""Capability graph: goal → capability subgraph with deterministic caching.

Completed from the committed contract in tests/architecture/test_capability_gates.py
(Gates 1, 6, 7).  The graph is independent of the provider registry — the same
goal always resolves to the same subgraph and fingerprint regardless of which
providers are currently registered (Gate 7), so a planner can rely on
capability structure without importing provider names (Gates 1, 9).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CapabilityNode:
    capability_id: str = ""
    name: str = ""
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "version": self.version,
            "metadata": self.metadata,
        }


@dataclass
class Subgraph:
    """Resolved capability subgraph for a goal."""

    goal: str = ""
    nodes: list[CapabilityNode] = field(default_factory=list)
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "nodes": [n.to_dict() for n in self.nodes],
            "fingerprint": self.fingerprint,
        }


# Goal templates: keyword → ordered capability plan.  Deterministic content,
# deliberately provider-free.  "build web server" and "build android app"
# share the same template → same subgraph (Gate 6 cache-template test).
_GOAL_TEMPLATES: list[tuple[tuple[str, ...], list[str]]] = [
    (("research", "investigate", "documentation", "compare"), ["research", "browser"]),
    (("web", "server", "api", "backend", "android", "app", "build", "full stack"),
     ["coding", "testing", "deployment"]),
    (("test", "unit test", "qa"), ["testing"]),
    (("review", "audit", "inspect"), ["review", "coding"]),
    (("secure", "security"), ["coding", "review"]),
    (("refactor",), ["coding", "testing"]),
    (("debug", "fix"), ["coding", "testing"]),
    (("document",), ["coding", "documentation"]),
    (("deploy", "release"), ["deployment", "testing"]),
    (("browse", "web page", "navigate"), ["browser"]),
    (("email", "mail"), ["email"]),
    (("desktop", "screenshot", "window"), ["desktop"]),
    (("github", "pull request", "commit"), ["github", "git"]),
]

_DEFAULT_TEMPLATE = ["coding", "testing"]

_MAX_CACHE = 256


def _fingerprint_for(nodes: list[CapabilityNode]) -> str:
    payload = "|".join(f"{n.capability_id}:{n.version}" for n in nodes)
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


class CapabilityGraph:
    """Goal → subgraph resolver with an LRU-ish bounded cache."""

    def __init__(self) -> None:
        self._nodes: dict[str, CapabilityNode] = {}
        self._cache: dict[str, Subgraph] = {}
        self._hits = 0
        self._misses = 0

    # -- node registry ---------------------------------------------------

    def add_node(self, node: CapabilityNode) -> CapabilityNode:
        self._nodes[node.capability_id] = node
        self.invalidate()
        return node

    def get_node(self, capability_id: str) -> Optional[CapabilityNode]:
        return self._nodes.get(capability_id)

    def nodes(self) -> list[CapabilityNode]:
        return list(self._nodes.values())

    # -- goal resolution ---------------------------------------------------

    def _template_for(self, goal: str) -> list[str]:
        text = (goal or "").lower()
        for keywords, caps in _GOAL_TEMPLATES:
            if any(kw in text for kw in keywords):
                return list(caps)
        return list(_DEFAULT_TEMPLATE)

    def resolve_goal(self, goal: str) -> Subgraph:
        """Resolve a goal to its cached capability subgraph (deterministic)."""
        key = str(goal or "")
        cached = self._cache.get(key)
        if cached is not None:
            self._hits += 1
            return cached
        self._misses += 1
        caps = self._template_for(key)
        nodes: list[CapabilityNode] = []
        for i, cap in enumerate(caps):
            known = self._nodes.get(cap)
            nodes.append(CapabilityNode(
                capability_id=cap,
                name=known.name if known else cap.title(),
                version=known.version if known else 1,
            ))
        subgraph = Subgraph(
            goal=key,
            nodes=nodes,
            fingerprint=_fingerprint_for(nodes),
        )
        if len(self._cache) >= _MAX_CACHE:
            self._cache.clear()
        self._cache[key] = subgraph
        return subgraph

    # -- cache stats ---------------------------------------------------

    def cache_stats(self) -> dict[str, int]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "cached_subgraphs": len(self._cache),
        }

    def invalidate(self) -> None:
        self._cache.clear()


# Module-level singleton (gates import ``capability_graph`` directly).
capability_graph = CapabilityGraph()
