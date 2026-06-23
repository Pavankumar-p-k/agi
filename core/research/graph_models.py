"""Graph models — shared dataclasses and constants for the knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Edge type constants ─────────────────────────────────────────────────

EDGE_SUPPORTS = "SUPPORTS"
EDGE_CONTRADICTS = "CONTRADICTS"
EDGE_REFERENCES = "REFERENCES"
EDGE_DERIVED_FROM = "DERIVED_FROM"
EDGE_MENTIONS = "MENTIONS"
EDGE_RELATED_TO = "RELATED_TO"

ALL_EDGE_TYPES = frozenset({
    EDGE_SUPPORTS, EDGE_CONTRADICTS, EDGE_REFERENCES,
    EDGE_DERIVED_FROM, EDGE_MENTIONS, EDGE_RELATED_TO,
})


# ── Node types ──────────────────────────────────────────────────────────

NODE_FACT = "fact"
NODE_ENTITY = "entity"
NODE_CONCEPT = "concept"

ALL_NODE_TYPES = frozenset({NODE_FACT, NODE_ENTITY, NODE_CONCEPT})


@dataclass
class GraphNode:
    """A node in the knowledge graph."""
    node_id: str
    node_type: str
    label: str
    data: dict[str, Any] = field(default_factory=dict)
    edge_count: int = 0


@dataclass
class GraphEdge:
    """A directed edge between two knowledge graph nodes."""
    edge_id: str
    source_id: str
    target_id: str
    edge_type: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphQuery:
    """Result of a knowledge graph query."""
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    subgraph: dict[str, list[GraphNode | GraphEdge]] = field(default_factory=dict)
