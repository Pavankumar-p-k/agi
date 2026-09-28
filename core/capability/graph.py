"""CapabilityGraph — goal-to-capability-subgraph resolution with caching."""
from __future__ import annotations

import hashlib
import threading
from typing import Optional

from core.capability.models import (
    _BUILTIN_CAPABILITIES,
    CapabilityNode,
    Subgraph,
)

# Goal keyword -> capability ids contributed to the subgraph.
_GOAL_TEMPLATES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("build", "code", "implement", "write", "app"), ("coding", "testing")),
    (("research", "search", "find", "investigate"), ("research",)),
    (("deploy", "release", "ship"), ("deployment", "testing")),
    (("document", "doc", "explain"), ("documentation",)),
    (("review", "audit", "check"), ("review",)),
    (("secure", "security"), ("security",)),
    (("browse", "web"), ("research",)),
    (("test", "verify"), ("testing",)),
]


def _fingerprint_for(nodes: list) -> str:
    blob = "|".join(sorted(
        f"{n.capability_id}:{n.version}" for n in nodes))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class CapabilityGraph:
    """Resolves goals to capability subgraphs, cached by goal string."""

    def __init__(self) -> None:
        self._cache: dict[str, Subgraph] = {}
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def resolve_goal(self, goal: str) -> Subgraph:
        key = str(goal or "")
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._hits += 1
                return cached

        g = key.lower()
        node_ids: list[str] = []
        for keywords, caps in _GOAL_TEMPLATES:
            if any(k in g for k in keywords):
                for c in caps:
                    if c not in node_ids:
                        node_ids.append(c)
        if not node_ids:
            node_ids = ["chat"]

        nodes = [CapabilityNode(capability_id=c,
                                version=1) for c in node_ids]
        subgraph = Subgraph(nodes=nodes, fingerprint=_fingerprint_for(nodes))

        with self._lock:
            self._cache[key] = subgraph
            self._misses += 1
        return subgraph

    def cache_stats(self) -> dict:
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "cached_subgraphs": len(self._cache),
            }

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


# Module-level default graph.
capability_graph = CapabilityGraph()


__all__ = ["CapabilityGraph", "capability_graph", "_BUILTIN_CAPABILITIES"]
