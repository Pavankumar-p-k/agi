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
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.models import Fact, Claim, Evidence, Source, KnowledgeGraph, GraphNode, GraphEdge
from core.research.evidence_tracker import EvidenceTracker

logger = logging.getLogger("jarvis.research.linker")


class Linker:
    """Links extracted facts, claims, and evidence into a coherent knowledge structure.
    
    Responsibilities:
    - Entity resolution (deduplication across sources)
    - Claim-evidence linking
    - Knowledge graph population
    - Contradiction detection
    - Source reliability tracking
    """
    
    def __init__(self, evidence_tracker: EvidenceTracker = None,
                 knowledge_graph: KnowledgeGraph = None):
        self.evidence_tracker = evidence_tracker or EvidenceTracker()
        self.knowledge_graph = knowledge_graph or KnowledgeGraph()
        self.resolved_entities: Dict[str, str] = {}  # alias -> canonical entity id
        self.link_statistics: Dict[str, Any] = {}
    
    def link_facts_to_claims(self, facts: List[Fact], claim_text: str = "") -> List[Claim]:
        """Link extracted facts to claims, creating or updating claims as needed."""
        claims = []
        
        if not facts:
            return claims
        
        # If we have a specific claim text, create/update that claim
        if claim_text:
            existing_claim = self.evidence_tracker.get_claim(claim_text[:50])  # Use hash-like lookup
            # Actually, let's create or find a claim matching this text
            claim_id = self._find_or_create_claim(claim_text)
            claim = self.evidence_tracker.get_claim(claim_id)
            
            # Link all facts to this claim
            for fact in facts:
                evidence = Evidence(
                    id=f"ev_{fact.id}",
                    claim=claim_text,
                    source_url=fact.source_url,
                    source_title=fact.source_title,
                    content=fact.text,
                    relevance=fact.confidence,
                    confidence=fact.confidence,
                )
                self.evidence_tracker.link_evidence_to_claim(evidence, claim)
                claims.append(claim)
        else:
            # Group facts by similarity and create claims for each group
            groups = self._group_facts_by_similarity(facts)
            
            for group_text, group_facts in groups:
                claim_id = self._find_or_create_claim(group_text)
                claim = self.evidence_tracker.get_claim(claim_id)
                
                for fact in group_facts:
                    evidence = Evidence(
                        id=f"ev_{fact.id}",
                        claim=group_text,
                        source_url=fact.source_url,
                        source_title=fact.source_title,
                        content=fact.text,
                        relevance=fact.confidence,
                        confidence=fact.confidence,
                    )
                    self.evidence_tracker.link_evidence_to_claim(evidence, claim)
                
                claims.append(claim)
        
        # Update knowledge graph after linking
        self._update_knowledge_graph()
        
        return claims
    
    def _find_or_create_claim(self, text: str) -> str:
        """Find existing claim or create a new one."""
        # Check if a claim with similar text already exists
        for claim_id, claim in self.evidence_tracker.claims.items():
            if text.lower() in claim.text.lower() or claim.text.lower() in text.lower():
                return claim_id
        
        # Create new claim
        claim = self.evidence_tracker.create_claim(text)
        return claim.id
    
    def _group_facts_by_similarity(self, facts: List[Fact]) -> List[tuple]:
        """Group facts by semantic similarity into claim groups."""
        groups: List[tuple] = []  # (group_representative_text, [facts])
        
        for fact in facts:
            added_to_group = False
            
            for i, (rep_text, group_facts) in enumerate(groups):
                # Simple similarity: word overlap
                fact_words = set(fact.text.lower().split())
                rep_words = set(rep_text.lower().split())
                
                if fact_words and rep_words:
                    overlap = len(fact_words & rep_words) / max(len(fact_words), len(rep_words))
                    if overlap > 0.5:  # 50% overlap = same group
                        groups[i] = (rep_text, group_facts + [fact])
                        added_to_group = True
                        break
            
            if not added_to_group:
                groups.append((fact.text, [fact]))
        
        return groups
    
    def detect_contradictions(self, claim_id: str = None) -> Dict[str, Any]:
        """Detect contradictions between claims or their evidence."""
        if claim_id:
            claim = self.evidence_tracker.get_claim(claim_id)
            if not claim:
                return {"error": f"Claim {claim_id} not found"}
            
            evidence_ids = claim.evidence_ids or []
            contradictions = []
            
            for eid in evidence_ids:
                if eid in self.evidence_tracker.evidence_index:
                    for cid in self.evidence_tracker.evidence_index[eid]:
                        other_claim = self.evidence_tracker.claims.get(cid)
                        if other_claim and other_claim.id != claim_id:
                            # Check if claims have opposite status
                            if claim.status == "supported" and other_claim.status == "contradicted":
                                contradictions.append({
                                    "claim_a": claim.text[:100],
                                    "claim_b": other_claim.text[:100],
                                    "evidence_id": eid,
                                })
            
            return {
                "claim_id": claim_id,
                "contradictions_found": len(contradictions),
                "contradictions": contradictions,
            }
        else:
            # Check all claims for contradictions
            all_contradictions = []
            for cid in self.evidence_tracker.claims:
                result = self.detect_contradictions(cid)
                if result.get("contradictions"):
                    all_contradictions.extend(result["contradictions"])
            
            return {
                "total_contradictions": len(all_contradictions),
                "contradictions": all_contradictions,
            }
    
    def update_knowledge_graph(self) -> None:
        """Update the knowledge graph with current claims and evidence."""
        # Add claims as nodes
        for claim_id, claim in self.evidence_tracker.claims.items():
            node = GraphNode(
                id=claim_id,
                label=claim.text[:80] if claim.text else "unnamed claim",
                node_type="claim",
                properties={"status": claim.status, "confidence": claim.confidence},
            )
            self.knowledge_graph.add_node(node)
        
        # Add evidence nodes
        for eid in self.evidence_tracker.evidence_index:
            # Find associated claim
            associated_claims = self.evidence_tracker.evidence_index[eid]
            if associated_claims:
                claim_id = associated_claims[0]
                claim = self.evidence_tracker.claims.get(claim_id)
                if claim:
                    node = GraphNode(
                        id=eid,
                        label=f"evidence: {claim.text[:50] if claim.text else ''}",
                        node_type="evidence",
                        properties={"claim_id": claim_id},
                    )
                    self.knowledge_graph.add_node(node)
        
        # Detect and add edges for contradictions
        contrad_result = self.detect_contradictions()
        for contrad in contrad_result.get("contradictions", []):
            # Find the claim nodes
            claim_a = self.evidence_tracker.claims.get(
                contrad.get("claim_a", "")[:50] if isinstance(contrad.get("claim_a"), str) else ""
            )
            claim_b = self.evidence_tracker.claims.get(
                contrad.get("claim_b", "")[:50] if isinstance(contrad.get("claim_b"), str) else ""
            )
            
            if claim_a and claim_b:
                edge = GraphEdge(
                    source_id=claim_a.id,
                    target_id=claim_b.id,
                    edge_type=EdgeType.CONTRADICTS,
                    properties={"detected_by": "Linker.detect_contradictions"},
                )
                self.knowledge_graph.add_edge(edge)
    
    def resolve_entity_aliases(self, entity_text: str) -> str:
        """Resolve entity alias to canonical form."""
        # Check if we've seen this entity before
        if entity_text in self.resolved_entities:
            return self.resolved_entities[entity_text]
        
        # Simple: use the text itself as canonical
        # In a full system, would do fuzzy matching against known entities
        self.resolved_entities[entity_text] = entity_text
        return entity_text
    
    def get_link_statistics(self) -> Dict[str, Any]:
        """Get linking statistics."""
        total_claims = len(self.evidence_tracker.claims)
        supported = len(self.evidence_tracker.get_supported_claims())
        contradicted = len(self.evidence_tracker.get_contradicted_claims())
        
        return {
            "total_claims": total_claims,
            "supported_claims": supported,
            "contradicted_claims": contradicted,
            "entity_aliases_resolved": len(self.resolved_entities),
            "knowledge_graph_nodes": len(self.knowledge_graph.nodes),
            "knowledge_graph_edges": len(self.knowledge_graph.edges),
        }