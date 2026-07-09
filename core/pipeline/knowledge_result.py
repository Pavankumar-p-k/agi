"""Frozen contract for the Knowledge stage output.

``KnowledgeResult`` is the single canonical artifact produced by the
Knowledge stage and consumed by the Reasoning stage.  It wraps the
existing ``core/research/knowledge_graph.py`` engine behind a typed,
frozen, deterministic, and replayable contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.research.graph_models import GraphEdge, GraphNode


@dataclass(frozen=True)
class KnowledgeResult:
    """Canonical output of the Knowledge stage.

    Every downstream stage (Reasoning, Planner) reads from this artifact.
    No other stage may construct a ``KnowledgeResult`` (enforced by
    architecture Rule 50).
    """

    knowledge_id: str
    """Unique identifier for this knowledge pass."""

    activity_id: str
    """Activity graph node id this knowledge is attached to."""

    entities: tuple[GraphNode, ...] = ()
    """Entity nodes extracted from the request context."""

    facts: tuple[GraphNode, ...] = ()
    """Fact nodes linked to entities."""

    edges: tuple[GraphEdge, ...] = ()
    """Edges connecting entities and facts."""

    node_count: int = 0
    """Total nodes in the knowledge graph for this request."""

    edge_count: int = 0
    """Total edges in the knowledge graph for this request."""

    metadata: Mapping[str, Any] = field(default_factory=dict)
    """Extensible bag for stage-specific metadata."""
