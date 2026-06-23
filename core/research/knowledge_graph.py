"""KnowledgeGraph — connected knowledge from facts, entities, and concepts.

Wraps GraphStore + Linker into a high-level API for building and
querying a knowledge graph from extracted facts.
"""

from __future__ import annotations

import logging
from typing import Any

from core.research.graph_models import (
    EDGE_CONTRADICTS,
    EDGE_REFERENCES,
    GraphEdge,
    GraphNode,
    GraphQuery,
    NODE_ENTITY,
    NODE_FACT,
)
from core.research.graph_store import GraphStore
from core.research.linker import Linker
from core.research.models import Fact

logger = logging.getLogger(__name__)




logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """High-level knowledge graph over extracted facts.

    Usage:
        store = GraphStore()
        kg = KnowledgeGraph(store)
        kg.add_fact(fact)
        kg.add_fact(fact2)
        result = kg.query_entity("Company X")
        for edge in result.edges:
            print(edge.edge_type, edge.source_id, "->", edge.target_id)
    """

    def __init__(self, store: GraphStore, linker: Linker | None = None):
        self._store = store
        self._linker = linker or Linker()

    # ── Fact ingestion ────────────────────────────────────────────────

    def add_fact(self, fact: Fact) -> list[str]:
        """Add a fact and all its entity/concept links to the graph.

        Returns list of edge IDs created.
        """
        edges_created: list[str] = []

        # 1. Create fact node
        fact_node_id = self._ensure_fact_node(fact)

        # 2. Extract and create entities
        entities = self._linker.extract_entities(fact)
        for entity_name in entities:
            entity_id = self._ensure_entity_node(entity_name)
            edge_id = self._store.add_edge(
                source_id=fact_node_id,
                target_id=entity_id,
                edge_type=EDGE_REFERENCES,
                metadata={"claim_snippet": fact.claim[:100]},
            )
            edges_created.append(edge_id)

        # 3. Find and link to existing facts about same entities
        for entity_name in entities:
            existing_fact_ids = self._store.get_fact_ids_for_entity(entity_name)
            for existing_id in existing_fact_ids:
                if existing_id == fact_node_id:
                    continue
                existing_fact = self._store.get_fact_for_node(existing_id)
                if existing_fact is None:
                    continue

                edge_type = self._linker.classify_relationship(
                    fact, existing_fact
                )
                if edge_type is None:
                    continue

                edge_id = self._store.add_edge(
                    source_id=fact_node_id,
                    target_id=existing_id,
                    edge_type=edge_type,
                    metadata={"confidence": fact.confidence},
                )
                edges_created.append(edge_id)

                # Also add reverse edge for contradictory relationships
                if edge_type == EDGE_CONTRADICTS:
                    self._store.add_edge(
                        source_id=existing_id,
                        target_id=fact_node_id,
                        edge_type=EDGE_CONTRADICTS,
                        metadata={"confidence": existing_fact.confidence},
                    )

        logger.debug("KnowledgeGraph: added fact %s, %d edges",
                     fact.fact_id, len(edges_created))
        return edges_created

    def add_facts(self, facts: list[Fact]) -> list[str]:
        """Batch-add multiple facts."""
        all_edges: list[str] = []
        for f in facts:
            all_edges.extend(self.add_fact(f))
        return all_edges

    # ── Query ─────────────────────────────────────────────────────────

    def query_entity(self, entity_name: str, max_depth: int = 2) -> GraphQuery:
        """Query the graph for all nodes/edges related to an entity."""
        entity_nodes = self._store.find_nodes_by_label(entity_name, NODE_ENTITY)
        if not entity_nodes:
            return GraphQuery()

        entity_id = entity_nodes[0].node_id
        return self._traverse(entity_id, max_depth)

    def query_fact(self, fact_id: str, max_depth: int = 2) -> GraphQuery:
        """Query the graph for connections from a specific fact."""
        node = self._store.get_node(fact_id)
        if node is None:
            return GraphQuery()
        return self._traverse(fact_id, max_depth)

    def get_contradictions(self, entity_name: str) -> list[GraphEdge]:
        """Get all contradictory edges involving an entity."""
        return self._store.find_edges_by_type(entity_name, EDGE_CONTRADICTS)

    def get_supports(self, entity_name: str) -> list[GraphEdge]:
        """Get all supporting/corroborating edges involving an entity."""
        return self._store.find_edges_by_type(entity_name, EDGE_SUPPORTS)

    def get_entity_facts(self, entity_name: str) -> list[GraphNode]:
        """Get all fact nodes that reference an entity."""
        entity_nodes = self._store.find_nodes_by_label(entity_name, NODE_ENTITY)
        if not entity_nodes:
            return []
        return self._store.get_linked_nodes(entity_nodes[0].node_id, EDGE_REFERENCES)

    def get_connected_entities(self, fact_id: str) -> list[GraphNode]:
        """Get all entities referenced by a fact node."""
        return self._store.get_linked_nodes(fact_id, EDGE_REFERENCES)

    def traverse(self, start_label: str, max_depth: int = 2) -> GraphQuery:
        """Traverse the graph starting from a label (entity or fact)."""
        nodes = self._store.find_nodes_by_label(start_label)
        if not nodes:
            return GraphQuery()
        return self._traverse(nodes[0].node_id, max_depth)

    def get_all_entities(self) -> list[GraphNode]:
        """List all entity nodes."""
        return self._store.list_nodes(NODE_ENTITY)

    def get_all_fact_nodes(self) -> list[GraphNode]:
        """List all fact nodes."""
        return self._store.list_nodes(NODE_FACT)

    def get_statistics(self) -> dict[str, Any]:
        """Return graph statistics."""
        nodes = self._store.count_nodes()
        edges = self._store.count_edges()
        return {
            "total_nodes": sum(nodes.values()),
            "nodes_by_type": dict(nodes),
            "total_edges": sum(edges.values()),
            "edges_by_type": dict(edges),
        }

    # ── Internals ─────────────────────────────────────────────────────

    def _ensure_fact_node(self, fact: Fact) -> str:
        """Create a fact node if it doesn't exist."""
        existing = self._store.get_node(fact.fact_id)
        if existing:
            return existing.node_id

        self._store.add_node(
            node_id=fact.fact_id,
            node_type=NODE_FACT,
            label=fact.claim[:120],
            data={
                "fact_id": fact.fact_id,
                "source_url": fact.source_url,
                "claim": fact.claim,
                "confidence": fact.confidence,
                "category": fact.category,
                "tags": fact.tags,
                "timestamp": fact.timestamp.isoformat() if fact.timestamp else None,
            },
        )
        return fact.fact_id

    def _ensure_entity_node(self, entity_name: str) -> str:
        """Create an entity node if it doesn't exist."""
        existing = self._store.find_nodes_by_label(entity_name, NODE_ENTITY)
        if existing:
            return existing[0].node_id

        entity_id = f"ent_{entity_name.lower().replace(' ', '_').replace('.', '')}"
        self._store.add_node(
            node_id=entity_id,
            node_type=NODE_ENTITY,
            label=entity_name,
            data={"name": entity_name},
        )
        return entity_id

    def _traverse(self, start_id: str, max_depth: int) -> GraphQuery:
        """BFS traversal from a start node."""
        visited: set[str] = set()
        all_nodes: dict[str, GraphNode] = {}
        all_edges: dict[str, GraphEdge] = {}
        current_level: list[str] = [start_id]

        for depth in range(max_depth + 1):
            next_level: list[str] = []
            for node_id in current_level:
                if node_id in visited:
                    continue
                visited.add(node_id)

                node = self._store.get_node(node_id)
                if node:
                    all_nodes[node_id] = node

                edges, neighbors = self._store.get_edges_and_neighbors(node_id)
                for edge in edges:
                    all_edges[edge.edge_id] = edge
                for nid in neighbors:
                    if nid not in visited:
                        next_level.append(nid)

            current_level = next_level

        return GraphQuery(
            nodes=list(all_nodes.values()),
            edges=list(all_edges.values()),
        )
