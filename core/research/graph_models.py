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

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class EdgeType(Enum):
    """Types of edges in the knowledge graph."""
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    MENTIONS = "mentions"
    REFERENCES = "references"
    DERIVED_FROM = "derived_from"
    RELATED_TO = "related_to"


@dataclass
class GraphNode:
    """A node in the research knowledge graph."""
    id: str = field(default_factory=lambda: str(uuid4()))
    label: str = ""
    node_type: str = "entity"  # entity, claim, source, concept
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now())


def uuid4():
    import uuid
    return uuid.uuid4()


@dataclass
class GraphEdge:
    """An edge connecting two nodes in the knowledge graph."""
    id: str = field(default_factory=lambda: str(uuid4()))
    source_id: str = ""
    target_id: str = ""
    edge_type: EdgeType = EdgeType.RELATED_TO
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now())


class KnowledgeGraph:
    """Simple in-memory knowledge graph for research AI."""
    
    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, GraphEdge] = {}
    
    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node
    
    def add_edge(self, edge: GraphEdge) -> None:
        self.edges[edge.id] = edge
        # Also store reverse references
        if edge.source_id not in self._get_node_ids():
            pass  # node may be added later
        if edge.target_id not in self._get_node_ids():
            pass
    
    def _get_node_ids(self) -> List[str]:
        return list(self.nodes.keys())
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self.nodes.get(node_id)
    
    def get_neighbors(self, node_id: str, edge_type: EdgeType = None) -> List[GraphEdge]:
        """Get all edges from a node, optionally filtered by type."""
        results = []
        for edge in self.edges.values():
            if edge.source_id == node_id:
                if edge_type is None or edge.edge_type == edge_type:
                    results.append(edge)
        return results
    
    def get_incoming_edges(self, node_id: str, edge_type: EdgeType = None) -> List[GraphEdge]:
        """Get all edges pointing TO a node."""
        results = []
        for edge in self.edges.values():
            if edge.target_id == node_id:
                if edge_type is None or edge.edge_type == edge_type:
                    results.append(edge)
        return results
    
    def find_paths(self, start_id: str, end_id: str, max_hops: int = 3) -> List[List[GraphNode]]:
        """Find paths between two nodes via BFS."""
        if start_id not in self.nodes or end_id not in self.nodes:
            return []
        
        paths = []
        queue = [([self.nodes[start_id]], start_id, {start_id})]
        
        while queue:
            path, current_id, visited = queue.pop(0)
            
            if len(path) - 1 >= max_hops:
                continue
            
            for edge in self.get_neighbors(current_id):
                next_id = edge.target_id
                if next_id == end_id:
                    paths.append(path + [self.nodes[next_id]])
                elif next_id not in visited and next_id in self.nodes:
                    queue.append((path + [self.nodes[next_id]], next_id, visited | {next_id}))
        
        return paths