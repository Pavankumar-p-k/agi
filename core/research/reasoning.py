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

from core.research.models import Claim, Evidence, Fact, ResearchResult, ResearchConfidence, Source, Hypothesis, Belief, BeliefState, Conclusion, CounterHypothesis

logger = logging.getLogger("jarvis.research.reasoning")


class BeliefStateTracker:
    """Tracks belief states through the reasoning process."""

    def __init__(self):
        self.states: Dict[str, BeliefState] = {}

    def update_belief(self, belief_id: str, claim_id: str, new_state: str,
                      confidence: float, evidence_ids: List[str] = None) -> BeliefState:
        """Update a belief state based on new evidence."""
        from core.research.models import BeliefState

        state = BeliefState(
            id=belief_id,
            claim_id=claim_id,
            state=new_state,
            confidence=confidence,
            evidence_ids=evidence_ids or [],
            updated_at=datetime.now(),
        )

        self.states[belief_id] = state
        return state

    def get_belief(self, belief_id: str) -> Optional[BeliefState]:
        """Get a belief state by ID."""
        return self.states.get(belief_id)


class ReasoningEngine:
    """Core reasoning engine that processes claims, evidence, and generates conclusions."""

    def __init__(self, evidence_tracker: EvidenceTracker = None):
        self.evidence_tracker = evidence_tracker or EvidenceTracker()
        self.belief_tracker = BeliefStateTracker()

    def reason_from_evidence(self, claim: Claim) -> Conclusion:
        """Reason from available evidence to produce a conclusion about a claim."""
        evaluation = self.evidence_tracker.evaluate_evidence(claim) if hasattr(
            self.evidence_tracker, 'evaluate_evidence') else self._simple_evaluate(claim)

        conclusion = Conclusion(
            claim_id=claim.id,
            claim_text=claim.text,
            support_level=evaluation.get("support_level", "unverified"),
            confidence=evaluation.get("average_confidence", 0.5),
            supporting_evidence_count=evaluation.get("supported_count", 0),
            contradicting_evidence_count=evaluation.get("contradicted_count", 0),
            evidence_summary=evaluation.get("analysis", ""),
            overall_confidence=evaluation.get("average_confidence", 0.5),
        )

        # Update belief state
        belief_id = f"belief_{claim.id}"
        self.belief_tracker.update_belief(
            belief_id=belief_id,
            claim_id=claim.id,
            new_state=conclusion.support_level,
            confidence=conclusion.overall_confidence,
            evidence_ids=claim.evidence_ids or [],
        )

        return conclusion

    def _simple_evaluate(self, claim: Claim) -> Dict[str, Any]:
        """Simple evaluation fallback when full evidence tracker not available."""
        evidence_count = len(claim.evidence_ids) if claim.evidence_ids else 0

        if evidence_count == 0:
            return {
                "support_level": "unverified",
                "average_confidence": 0.1,
                "supported_count": 0,
                "contradicted_count": 0,
                "analysis": "No evidence available for evaluation",
            }
        elif evidence_count == 1:
            return {
                "support_level": "partially_supported",
                "average_confidence": claim.confidence if claim.confidence else 0.3,
                "supported_count": 1 if (claim.confidence or 0) > 0.5 else 0,
                "contradicted_count": 0 if (claim.confidence or 0) > 0.5 else 1,
                "analysis": "Single evidence item available",
            }
        else:
            return {
                "support_level": "supported" if evidence_count >= 3 else "partially_supported",
                "average_confidence": round(0.6 + 0.1 * min(evidence_count, 5), 2),
                "supported_count": min(evidence_count, 3),
                "contradicted_count": max(0, evidence_count - 3),
                "analysis": f"{evidence_count} evidence items evaluated",
            }

    def generate_counter_hypotheses(self, claim: Claim, max_hypotheses: int = 3) -> List[CounterHypothesis]:
        """Generate alternative hypotheses to explain the same evidence."""
        hypotheses = []

        # Based on gaps identified in the claim
        from core.research.reasoner import FactReasoner
        reasoner = FactReasoner(self.evidence_tracker)
        gaps = reasoner.identify_gaps(claim)

        for gap in gaps[:max_hypotheses]:
            # Create a counter-hypothesis from each gap
            hypothesis = CounterHypothesis(
                id=f"counter_{claim.id}_{len(hypotheses)}",
                text=f"Alternative explanation: {gap[:100]}",
                related_claim=claim.id,
                evidence_required=[],
                status="unsubstantiated",
                confidence=0.3,
            )
            hypotheses.append(hypothesis)

        return hypotheses

    def identify_missing_info(self, claim: Claim) -> List[str]:
        """Identify what information is still needed to reach a conclusion."""
        from core.research.reasoner import FactReasoner
        reasoner = FactReasoner(self.evidence_tracker)
        gaps = reasoner.identify_gaps(claim)

        # Convert gaps to missing info items
        missing = []
        for gap in gaps:
            # Extract what's needed from the gap
            if "evidence" in gap.lower():
                missing.append("additional evidence")
            if "confidence" in gap.lower() or "low" in gap.lower():
                missing.append("higher confidence verification")
            if "recent" in gap.lower():
                missing.append("more recent sources")
            if "diversity" in gap.lower():
                missing.append("more diverse sources")
            else:
                missing.append(gap)

        # Remove duplicates while preserving order
        seen = set()
        unique_missing = []
        for m in missing:
            if m not in seen:
                seen.add(m)
                unique_missing.append(m)

        return unique_missing if unique_missing else ["no significant gaps identified"]


class ArgumentMapper:
    """Maps arguments and counter-arguments in the research context."""

    def map_argument_chain(self, claim_id: str) -> Dict[str, Any]:
        """Map the argument chain starting from a claim."""
        claim = self.evidence_tracker.get_claim(claim_id)
        if not claim:
            return {"error": f"Claim {claim_id} not found"}

        # Find supporting evidence
        evidence_ids = claim.evidence_ids or []

        # Find claims supported by this evidence
        supporting_claims = []
        for eid in evidence_ids:
            if eid in self.evidence_tracker.evidence_index:
                for cid in self.evidence_tracker.evidence_index[eid]:
                    c = self.evidence_tracker.claims.get(cid)
                    if c and c.status == "supported":
                        supporting_claims.append({
                            "claim_id": c.id,
                            "text": c.text[:80],
                            "confidence": c.confidence,
                        })

        # Find contradicting claims
        contradicting_claims = []
        for eid in evidence_ids:
            if eid in self.evidence_tracker.evidence_index:
                for cid in self.evidence_tracker.evidence_index[eid]:
                    c = self.evidence_tracker.claims.get(cid)
                    if c and c.status == "contradicted":
                        contradicting_claims.append({
                            "claim_id": c.id,
                            "text": c.text[:80],
                            "confidence": c.confidence,
                        })

        return {
            "claim_text": claim.text,
            "supporting_claims": supporting_claims,
            "contradicting_claims": contradicting_claims,
            "evidence_count": len(evidence_ids),
        }