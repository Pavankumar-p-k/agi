# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.graph_models import GraphNode, GraphEdge, EdgeType, KnowledgeGraph

logger = logging.getLogger("jarvis.research.knowledge_graph")


class KnowledgeGraphManager:
    """Manages the research knowledge graph for entity resolution and relationship mapping."""

    def __init__(self, kg: KnowledgeGraph = None):
        self.kg = kg or KnowledgeGraph()
        self.entity_aliases: Dict[str, str] = {}  # alias -> canonical entity
        self.node_counter = 0

    def add_entity(self, text: str, entity_type: str = "entity",
                   properties: Dict[str, Any] = None) -> GraphNode:
        """Add an entity to the knowledge graph."""
        # Resolve alias
        canonical = self._resolve_alias(text)

        # Check if already exists
        if canonical in [n.label for n in self.kg.nodes if n.node_type == "entity"]:
            # Find existing node
            for node in self.kg.nodes:
                if node.label == canonical and node.node_type == "entity":
                    return node

        # Create new node
        self.node_counter += 1
        node = GraphNode(
            id=f"entity_{self.node_counter}",
            label=canonical,
            node_type=entity_type,
            properties=properties or {},
            created_at=datetime.now(),
        )

        self.kg.add_node(node)
        self.entity_aliases[text] = canonical
        return node

    def add_relationship(self, source: str, target: str,
                         relationship: str = "related_to",
                         properties: Dict[str, Any] = None) -> GraphEdge:
        """Add a relationship between two entities."""
        # Resolve aliases
        source_canonical = self._resolve_alias(source)
        target_canonical = self._resolve_alias(target)

        # Find or create nodes
        source_node = self._find_or_create_node(source_canonical, "entity")
        target_node = self._find_or_create_node(target_canonical, "entity")

        # Map relationship string to EdgeType
        edge_type_map = {
            "supports": EdgeType.SUPPORTS,
            "contradicts": EdgeType.CONTRADICTS,
            "mentions": EdgeType.MENTIONS,
            "references": EdgeType.REFERENCES,
            "derived_from": EdgeType.DERIVED_FROM,
            "related_to": EdgeType.RELATED_TO,
        }
        edge_type = edge_type_map.get(relationship, EdgeType.RELATED_TO)

        # Create edge
        edge = GraphEdge(
            id=f"edge_{self.node_counter + 1}",
            source_id=source_node.id,
            target_id=target_node.id,
            edge_type=edge_type,
            properties=properties or {},
            created_at=datetime.now(),
        )

        self.kg.add_edge(edge)
        return edge

    def _resolve_alias(self, text: str) -> str:
        """Resolve entity alias to canonical form."""
        text_lower = text.lower().strip()
        if text_lower in self.entity_aliases:
            return self.entity_aliases[text_lower]
        # Store as canonical (lowercase stripped)
        self.entity_aliases[text_lower] = text_lower
        return text_lower

    def _find_or_create_node(self, label: str, node_type: str = "entity") -> GraphNode:
        """Find existing node or create new one."""
        # Check if node exists
        for node in self.kg.nodes:
            if node.label.lower() == label.lower() and node.node_type == node_type:
                return node

        # Create new
        self.node_counter += 1
        node = GraphNode(
            id=f"entity_{self.node_counter}",
            label=label,
            node_type=node_type,
            properties={},
            created_at=datetime.now(),
        )
        self.kg.add_node(node)
        return node

    def find_path(self, start: str, end: str, max_hops: int = 3) -> List[Dict[str, Any]]:
        """Find a path between two entities."""
        start_canonical = self._resolve_alias(start)
        end_canonical = self._resolve_alias(end)

        # Find nodes
        start_node = None
        end_node = None
        for node in self.kg.nodes:
            if node.label.lower() == start_canonical and node.node_type == "entity":
                start_node = node
            if node.label.lower() == end_canonical and node.node_type == "entity":
                end_node = node

        if not start_node or not end_node:
            return []

        paths = self.kg.find_paths(start_node.id, end_node.id, max_hops)
        result_paths = []

        for path in paths:
            path_dict = []
            for node in path:
                path_dict.append({
                    "id": node.id,
                    "label": node.label,
                    "type": node.node_type,
                })
            result_paths.append(path_dict)

        return result_paths

    def find_related_entities(self, entity: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Find entities related to the given entity."""
        canonical = self._resolve_alias(entity)

        # Find node
        node = None
        for n in self.kg.nodes:
            if n.label.lower() == canonical and n.node_type == "entity":
                node = n
                break

        if not node:
            return []

        # Find edges from this node
        related = []
        for edge in self.kg.edges.values():
            if edge.source_id == node.id:
                # Find target node
                target = None
                for n in self.kg.nodes:
                    if n.id == edge.target_id:
                        target = n
                        break
                if target:
                    related.append({
                        "entity": target.label,
                        "relationship": edge.edge_type.value,
                        "properties": edge.properties,
                    })
            elif edge.target_id == node.id:
                # Find source node
                source = None
                for n in self.kg.nodes:
                    if n.id == edge.source_id:
                        source = n
                        break
                if source:
                    related.append({
                        "entity": source.label,
                        "relationship": edge.edge_type.value,
                        "properties": edge.properties,
                    })

        # Deduplicate by entity label
        seen = set()
        unique_related = []
        for r in related:
            if r["entity"] not in seen:
                seen.add(r["entity"])
                unique_related.append(r)

        return unique_related[:max_results]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize knowledge graph to dict."""
        return {
            "nodes": [{"id": n.id, "label": n.label, "type": n.node_type,
                       "properties": n.properties} for n in self.kg.nodes],
            "edges": [{"id": e.id, "source": e.source_id, "target": e.target_id,
                       "type": e.edge_type.value, "properties": e.properties}
                      for e in self.kg.edges],
            "entity_aliases": self.entity_aliases,
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Deserialize knowledge graph from dict."""
        self.entity_aliases = data.get("entity_aliases", {})

        for node_data in data.get("nodes", []):
            node = GraphNode(
                id=node_data["id"],
                label=node_data["label"],
                node_type=node_data.get("type", "entity"),
                properties=node_data.get("properties", {}),
                created_at=datetime.now(),
            )
            self.kg.add_node(node)

        for edge_data in data.get("edges", []):
            edge = GraphEdge(
                id=edge_data["id"],
                source_id=edge_data["source"],
                target_id=edge_data["target"],
                edge_type=EdgeType(edge_data.get("type", "related_to")),
                properties=edge_data.get("properties", {}),
                created_at=datetime.now(),
            )
            self.kg.add_edge(edge)