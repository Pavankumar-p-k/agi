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

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.models import Claim, Evidence, Fact, ResearchResult, ResearchConfidence

logger = logging.getLogger("jarvis.research.evidence_tracker")


class EvidenceTracker:
    """Tracks evidence for claims during research, enabling contradiction detection
    and confidence assessment."""
    
    def __init__(self):
        # In-memory storage; in production would use the JARVIS memory system
        self.claims: Dict[str, Claim] = {}
        self.evidence_index: Dict[str, List[str]] = {}  # source_id -> [claim_ids]
        self.claim_evidence: Dict[str, List[str]] = {}  # claim_id -> [evidence_ids]
    
    def create_claim(self, text: str, research_task_id: str = "") -> Claim:
        """Create a new claim for tracking."""
        claim = Claim(
            text=text,
            research_task_id=research_task_id,
        )
        claim_id = claim.id
        self.claims[claim_id] = claim
        self.claim_evidence[claim_id] = []
        return claim
    
    def link_evidence_to_claim(self, evidence: Evidence, claim: Claim) -> None:
        """Link an evidence item to a claim."""
        claim_id = claim.id
        evidence_id = evidence.id
        
        if claim_id not in self.claims:
            logger.error(f"Claim {claim_id} not found in tracker")
            return
        
        # Add evidence to claim
        if evidence_id not in self.claim_evidence[claim_id]:
            self.claim_evidence[claim_id].append(evidence_id)
        
        # Update evidence index
        if evidence_id not in self.evidence_index:
            self.evidence_index[evidence_id] = []
        if claim_id not in self.evidence_index[evidence_id]:
            self.evidence_index[evidence_id].append(claim_id)
        
        # Update claim's evidence list
        if evidence_id not in self.claim_evidence[claim_id]:
            # Ensure we're updating the right claim
            original = self.claims[claim_id]
            original.evidence_ids.append(evidence_id)
    
    def update_claim_status(self, claim_id: str, status: str, 
                           confidence: float = None) -> Optional[Claim]:
        """Update a claim's status and confidence."""
        if claim_id not in self.claims:
            logger.error(f"Claim {claim_id} not found")
            return None
        
        claim = self.claims[claim_id]
        claim.status = status
        if confidence is not None:
            claim.confidence = confidence
        
        # Adjust based on evidence
        self._recalculate_claim_status(claim)
        return claim
    
    def _recalculate_claim_status(self, claim: Claim) -> None:
        """Recalculate claim status based on linked evidence."""
        evidence_ids = claim.evidence_ids or []
        supported = 0
        contradicted = 0
        
        for eid in evidence_ids:
            if eid in self.evidence_index:
                # Check associated claims for this evidence
                for cid in self.evidence_index[eid]:
                    c = self.claims.get(cid)
                    if c and c.status == "supported":
                        supported += 1
                    if c and c.status == "contradicted":
                        contradicted += 1
        
        # Simple majority logic
        if supported > contradicted and supported > 0:
            claim.status = "supported"
        elif contradicted > supported and contradicted > 0:
            claim.status = "contradicted"
        else:
            claim.status = "unverified"
        
        # Adjust confidence based on evidence count
        if len(evidence_ids) >= 3:
            claim.confidence = min(1.0, 0.5 + 0.1 * len(evidence_ids))
        elif len(evidence_ids) >= 1:
            claim.confidence = min(1.0, 0.3 + 0.2 * len(evidence_ids))
        else:
            claim.confidence = 0.3
    
    def get_claim(self, claim_id: str) -> Optional[Claim]:
        """Get a claim by ID."""
        return self.claims.get(claim_id)
    
    def get_claims_by_status(self, status: str) -> List[Claim]:
        """Get all claims with a specific status."""
        return [c for c in self.claims.values() if c.status == status]
    
    def get_supported_claims(self) -> List[Claim]:
        """Get all supported claims."""
        return self.get_claims_by_status("supported")
    
    def get_contradicted_claims(self) -> List[Claim]:
        """Get all contradicted claims."""
        return self.get_claims_by_status("contradicted")
    
    def get_unverified_claims(self) -> List[Claim]:
        """Get all unverified claims."""
        return self.get_claims_by_status("unverified")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get tracker statistics."""
        total = len(self.claims)
        supported = len(self.get_supported_claims())
        contradicted = len(self.get_contradicted_claims())
        unverified = len(self.get_unverified_claims())
        
        return {
            "total_claims": total,
            "supported": supported,
            "contradicted": contradicted,
            "unverified": unverified,
            "support_rate": round(supported / total, 2) if total > 0 else 0.0,
            "contradiction_rate": round(contradicted / total, 2) if total > 0 else 0.0,
        }
    
    def export_for_report(self) -> ResearchConfidence:
        """Export statistics as ResearchConfidence for report generation."""
        stats = self.get_statistics()
        
        # Determine overall confidence
        if stats["support_rate"] > 0.6 and stats["contradiction_rate"] < 0.2:
            overall = 0.8
        elif stats["support_rate"] > 0.3:
            overall = 0.5
        else:
            overall = 0.2
        
        return ResearchConfidence(
            overall=overall,
            source_quality=stats["support_rate"],
            evidence_coverage=1.0 - stats["contradiction_rate"],
            contradiction_count=stats["contradicted"],
            missing_info=[]  # Would be computed from gaps
        )
    
    def clear(self) -> None:
        """Clear all tracked data."""
        self.claims.clear()
        self.evidence_index.clear()
        self.claim_evidence.clear()