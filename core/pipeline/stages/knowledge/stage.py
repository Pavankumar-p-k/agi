"""KnowledgeStage — canonical pipeline stage for knowledge graph integration.

Adapts the existing ``core/research/knowledge_graph.py`` and
``core/research/graph_store.py`` engines into the pipeline.

Pipeline position: after ContextRetrieval, before Reasoning.
"""
from __future__ import annotations

import uuid
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.knowledge_result import KnowledgeResult
from core.research.graph_models import NODE_ENTITY, NODE_FACT
from core.research.graph_store import GraphStore
from core.research.knowledge_graph import KnowledgeGraph
from core.research.models import Fact


class KnowledgeStage(PipelineStage):
    """Canonical knowledge graph stage.

    Front-door for all knowledge graph operations in the pipeline.
    Delegates to the existing ``core/research/`` graph engines.
    """

    def __init__(self, graph_store: GraphStore | None = None) -> None:
        self._store = graph_store or GraphStore()
        self._kg = KnowledgeGraph(self._store)

    @property
    def name(self) -> str:
        return "knowledge"

    async def execute(self, context: PipelineContext) -> StageResult:
        raw_input = context.raw_input or ""
        retrieved = context.retrieved_context or {}

        # Collect facts from retrieved context
        facts = self._collect_facts(raw_input, retrieved)

        # Add facts to knowledge graph
        for fact in facts:
            self._kg.add_fact(fact)

        # Query graph for entities matching this request
        entities = self._store.find_nodes_by_label(raw_input[:50], node_type=NODE_ENTITY)
        fact_nodes = self._store.list_nodes(node_type=NODE_FACT)

        # Get all edges for the relevant subgraph
        entity_ids = {e.node_id for e in entities}
        all_edges: list[Any] = []
        for eid in entity_ids:
            edges_from = self._store.get_outgoing_edges(eid)
            edges_to = self._store.get_incoming_edges(eid)
            all_edges.extend(edges_from)
            all_edges.extend(edges_to)

        # Deduplicate edges by edge_id
        seen: set[str] = set()
        unique_edges: list[Any] = []
        for e in all_edges:
            if e.edge_id not in seen:
                seen.add(e.edge_id)
                unique_edges.append(e)

        # Build the result
        knowledge_id = _make_knowledge_id(context.services)
        result = KnowledgeResult(
            knowledge_id=knowledge_id,
            activity_id=context.activity_id or "",
            entities=tuple(entities),
            facts=tuple(fact_nodes),
            edges=tuple(unique_edges),
            node_count=len(entities) + len(fact_nodes),
            edge_count=len(unique_edges),
            metadata={
                "facts_ingested": len(facts),
                "entity_count": len(entities),
                "fact_count": len(fact_nodes),
            },
        )

        context.knowledge_result = result

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    def _collect_facts(
        self, raw_input: str, retrieved: dict[str, Any],
    ) -> list[Fact]:
        facts: list[Fact] = []
        if not retrieved:
            return facts

        memories = retrieved.get("memories", [])
        for mem in memories:
            content = ""
            source_url = ""
            confidence = 0.5
            if isinstance(mem, dict):
                content = mem.get("content", mem.get("text", ""))
                source_url = mem.get("source_url", "")
                confidence = mem.get("confidence", 0.5)
            elif hasattr(mem, "content"):
                content = getattr(mem, "content")
            if content:
                facts.append(Fact(
                    fact_id=f"fact_{len(facts)}",
                    source_url=source_url,
                    claim=content if isinstance(content, str) else str(content),
                    confidence=confidence,
                ))
        return facts


def _make_knowledge_id(services: Any) -> str:
    """Generate a deterministic or random knowledge id."""
    raw = services.uuid4()
    if isinstance(raw, str):
        return f"kn_{raw[:24]}"
    return f"kn_{raw.hex[:24]}"
