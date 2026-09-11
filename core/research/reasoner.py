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

from core.research.models import Claim, Evidence, Fact, ResearchResult, ResearchConfidence, Source, Hypothesis
from core.research.evidence_tracker import EvidenceTracker

logger = logging.getLogger("jarvis.research.reasoner")


class FactReasoner:
    """Reasons about extracted facts to determine support, contradiction, and confidence."""

    def __init__(self, evidence_tracker: EvidenceTracker = None):
        self.evidence_tracker = evidence_tracker or EvidenceTracker()

    def compare_claims(self, claim_id_a: str, claim_id_b: str) -> Dict[str, Any]:
        """Compare two claims and determine their relationship."""
        claim_a = self.evidence_tracker.get_claim(claim_id_a)
        claim_b = self.evidence_tracker.get_claim(claim_id_b)

        if not claim_a or not claim_b:
            return {"error": "One or both claims not found"}

        # Analyze evidence overlap
        evidence_a = claim_a.evidence_ids or []
        evidence_b = claim_b.evidence_ids or []

        shared_evidence = set(evidence_a) & set(evidence_b)
        unique_a = set(evidence_a) - set(evidence_b)
        unique_b = set(evidence_b) - set(evidence_a)

        # Determine relationship
        relationship = "independent"
        if shared_evidence:
            relationship = "shared_evidence"
        if claim_a.status == "supported" and claim_b.status == "contradicted":
            relationship = "contradictory"
        if claim_a.status == "contradicted" and claim_b.status == "supported":
            relationship = "contradictory"
        if claim_a.status == "supported" and claim_b.status == "supported":
            relationship = "supportive"

        # Calculate confidence differences
        confidence_diff = abs(claim_a.confidence - claim_b.confidence)

        return {
            "claim_a_id": claim_id_a,
            "claim_b_id": claim_id_b,
            "relationship": relationship,
            "shared_evidence_count": len(shared_evidence),
            "unique_to_a": len(unique_a),
            "unique_to_b": len(unique_b),
            "confidence_a": claim_a.confidence,
            "confidence_b": claim_b.confidence,
            "confidence_difference": round(confidence_diff, 2),
        }

    def evaluate_evidence(self, claim: Claim) -> Dict[str, Any]:
        """Evaluate all evidence for a claim and determine support level."""
        evidence_ids = claim.evidence_ids or []

        if not evidence_ids:
            return {
                "claim_text": claim.text,
                "support_level": "unverified",
                "evidence_count": 0,
                "analysis": "No evidence linked to this claim",
            }

        # Count evidence by relevance and confidence
        total_relevance = 0.0
        total_confidence = 0.0
        supported_count = 0
        contradicted_count = 0

        for eid in evidence_ids:
            if eid in self.evidence_tracker.evidence_index:
                # Find associated claims for this evidence
                for cid in self.evidence_tracker.evidence_index[eid]:
                    c = self.evidence_tracker.claims.get(cid)
                    if c:
                        total_relevance += c.confidence or 0.5
                        total_confidence += c.confidence or 0.5

                        if c.status == "supported":
                            supported_count += 1
                        if c.status == "contradicted":
                            contradicted_count += 1

        # Determine overall support level
        evidence_count = len(evidence_ids)
        if supported_count > contradicted_count and supported_count > 0:
            support_level = "supported"
        elif contradicted_count > supported_count and contradicted_count > 0:
            support_level = "contradicted"
        elif supported_count > 0:
            support_level = "partially_supported"
        else:
            support_level = "unverified"

        # Calculate average confidence
        avg_confidence = round(total_confidence / max(1, evidence_count), 2)

        # Generate analysis summary
        analysis_parts = []
        if evidence_count > 0:
            analysis_parts.append(f"{evidence_count} evidence item(s)")
        if supported_count > 0:
            analysis_parts.append(f"{supported_count} supporting")
        if contradicted_count > 0:
            analysis_parts.append(f"{contradicted_count} contradicting")
        if not analysis_parts:
            analysis_parts.append("no clear pattern")

        analysis = ". ".join(analysis_parts) + "."

        return {
            "claim_text": claim.text,
            "support_level": support_level,
            "evidence_count": evidence_count,
            "supported_count": supported_count,
            "contradicted_count": contradicted_count,
            "average_confidence": avg_confidence,
            "analysis": analysis,
        }

    def identify_gaps(self, claim: Claim) -> List[str]:
        """Identify what information is missing to substantiate a claim."""
        evidence_ids = claim.evidence_ids or []

        gaps = []

        if not evidence_ids:
            gaps.append("No evidence linked to this claim")
            return gaps

        # Check evidence coverage
        evidence_count = len(evidence_ids)
        if evidence_count < 3:
            gaps.append(f"Only {evidence_count} evidence item(s) — more evidence recommended")

        # Check for contradicting evidence
        contradicted = 0
        for eid in evidence_ids:
            if eid in self.evidence_tracker.evidence_index:
                for cid in self.evidence_tracker.evidence_index[eid]:
                    c = self.evidence_tracker.claims.get(cid)
                    if c and c.status == "contradicted":
                        contradicted += 1

        if contradicted > 0:
            gaps.append(f"{contradicted} piece(s) of evidence contradict this claim")

        # Check confidence threshold
        if claim.confidence < 0.5:
            gaps.append("Low confidence — additional verification needed")

        # Specific gap types
        if evidence_count > 0:
            # Check if we have recent evidence
            from datetime import datetime
            recent_evidence = 0
            for eid in evidence_ids:
                if eid in self.evidence_tracker.evidence_index:
                    for cid in self.evidence_tracker.evidence_index[eid]:
                        c = self.evidence_tracker.claims.get(cid)
                        if c and c.created_at:
                            age = (datetime.now() - c.created_at).days
                            if age < 365:
                                recent_evidence += 1

            if recent_evidence == 0:
                gaps.append("No recent evidence — consider updating with newer sources")

            # Check diversity of sources
            source_types = set()
            for eid in evidence_ids:
                if eid in self.evidence_tracker.evidence_index:
                    for cid in self.evidence_tracker.evidence_index[eid]:
                        c = self.evidence_tracker.claims.get(cid)
                        if c and c.source_url:
                            import re
                            domain = re.search(r"https?://[^/]+", c.source_url)
                            if domain:
                                source_types.add(domain.group(0))

            if len(source_types) < 3 and evidence_count >= 3:
                gaps.append("Limited source diversity — consider broader sources")

        return gaps


class ComparisonEngine:
    """Compares multiple sources, hypotheses, or explanations."""

    @staticmethod
    def compare_hypotheses(hypothesis_a: Hypothesis, hypothesis_b: Hypothesis) -> Dict[str, Any]:
        """Compare two hypotheses and evaluate which is better supported."""
        # Compare supporting/contradicting evidence overlap
        supporting_overlap = set(hypothesis_a.supporting_evidence) & set(hypothesis_b.supporting_evidence)
        contradicting_a_in_b = set(hypothesis_a.contradicting_evidence) & set(hypothesis_b.supporting_evidence)
        contradicting_b_in_a = set(hypothesis_b.contradicting_evidence) & set(hypothesis_a.supporting_evidence)

        # Determine better supported
        a_support = len(hypothesis_a.supporting_evidence)
        b_support = len(hypothesis_b.supporting_evidence)

        # Check for direct contradiction
        is_contradiction = (
            hypothesis_b.text.lower() in hypothesis_a.text.lower()
            or hypothesis_a.text.lower() in hypothesis_b.text.lower()
        )

        if is_contradiction:
            relationship = "contradictory"
        elif a_support > b_support * 1.5:
            relationship = "a_better_supported"
        elif b_support > a_support * 1.5:
            relationship = "b_better_supported"
        else:
            relationship = "inconclusive"

        return {
            "hypothesis_a_id": hypothesis_a.id,
            "hypothesis_b_id": hypothesis_b.id,
            "relationship": relationship,
            "a_supporting_evidence": a_support,
            "b_supporting_evidence": b_support,
            "shared_supporting": len(supporting_overlap),
            "a_contradicting_b_evidence": len(contradicting_a_in_b),
            "b_contradicting_a_evidence": len(contradicting_b_in_a),
            "recommended": hypothesis_a.id if a_support > b_support else hypothesis_b.id if b_support > a_support else None,
        }