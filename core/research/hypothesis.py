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

from core.research.models import Hypothesis, Fact, Claim, Evidence, ResearchResult
from core.research.evidence_tracker import EvidenceTracker
from core.research.reasoner import FactReasoner

logger = logging.getLogger("jarvis.research.hypothesis")


class HypothesisGenerator:
    """Generates and evaluates hypotheses during research."""

    def __init__(self, evidence_tracker=None, reasoner=None):
        self.evidence_tracker = evidence_tracker or EvidenceTracker()
        self.reasoner = reasoner or FactReasoner(self.evidence_tracker)

    def generate_hypotheses(self, claim: Claim, max_hypotheses: int = 3) -> List[Hypothesis]:
        """Generate hypotheses to explain a claim's evidence."""
        hypotheses = []

        # Analyze the claim and its evidence
        evidence_ids = claim.evidence_ids or []
        if not evidence_ids:
            # No evidence - generate broad hypotheses from the claim text
            return self._generate_broad_hypotheses(claim.text, max_hypotheses)

        # Generate hypotheses based on evidence patterns
        for i in range(max_hypotheses):
            hypothesis = self._create_hypothesis_from_evidence(claim, evidence_ids, i)
            if hypothesis:
                hypotheses.append(hypothesis)

        # If we have fewer hypotheses than requested, fill with broad ones
        while len(hypotheses) < max_hypotheses:
            hyp = self._generate_broad_hypothesis_from_claim(claim, len(hypotheses))
            if hyp and hyp not in hypotheses:
                hypotheses.append(hyp)

        return hypotheses[:max_hypotheses]

    def _generate_broad_hypotheses(self, claim_text: str, max_hypotheses: int) -> List[Hypothesis]:
        """Generate broad hypotheses from claim text when no evidence available."""
        hypotheses = []
        sentences = [s.strip() for s in claim_text.split('.') if s.strip()]

        for i, sentence in enumerate(sentences[:max_hypotheses]):
            hyp = Hypothesis(
                id=f"hyp_broad_{i}",
                text=f"Based on the claim: {sentence[:150]}",
                related_claim="",
                evidence_required=[],
                status="unsubstantiated",
                confidence=0.3,
            )
            hypotheses.append(hyp)

        return hypotheses if hypotheses else [
            Hypothesis(
                id="hyp_broad_0",
                text="The available evidence supports the claim but requires further verification",
                related_claim="",
                evidence_required=[],
                status="unsubstantiated",
                confidence=0.4,
            )
        ]

    def _create_hypothesis_from_evidence(self, claim: Claim, evidence_ids: List[str],
                                          index: int) -> Optional[Hypothesis]:
        """Create a hypothesis based on available evidence patterns."""
        if not evidence_ids:
            return None

        # Analyze associated claims for this evidence
        associated_claims = []
        for eid in evidence_ids[:3]:  # Top 3 evidence items
            if eid in self.evidence_tracker.evidence_index:
                for cid in self.evidence_tracker.evidence_index[eid]:
                    c = self.evidence_tracker.claims.get(cid)
                    if c:
                        associated_claims.append(c)

        if not associated_claims:
            return self._generate_broad_hypotheses(claim.text, 1)[0]

        # Create hypothesis based on the most supported claim's pattern
        most_supported = max(associated_claims, key=lambda c: c.confidence or 0)

        hyp = Hypothesis(
            id=f"hyp_evidence_{index}",
            text=f"Evidence suggests: {most_supported.text[:150]}...",
            related_claim=claim.id,
            evidence_required=evidence_ids[:3],
            status="unsubstantiated",
            confidence=most_supported.confidence if most_supported.confidence else 0.5,
        )

        return hyp

    def _generate_broad_hypothesis_from_claim(self, claim: Claim, index: int) -> Optional[Hypothesis]:
        """Generate a broad hypothesis directly from a claim."""
        return Hypothesis(
            id=f"hyp_claim_{index}",
            text=f"The claim that '{claim.text[:80]}...' may have multiple explanations",
            related_claim=claim.id,
            evidence_required=[],
            status="unsubstantiated",
            confidence=0.3 + index * 0.1,
        )

    def evaluate_hypothesis(self, hypothesis: Hypothesis, claim: Claim) -> Dict[str, Any]:
        """Evaluate a hypothesis against available evidence and claims."""
        evidence_ids = claim.evidence_ids or []

        if not evidence_ids:
            return {
                "hypothesis_id": hypothesis.id,
                "support_level": "unsubstantiated",
                "confidence_adjustment": 0.0,
                "evidence_match": 0,
                "reasoning": "No evidence available for evaluation",
            }

        # Count how many evidence items support vs contradict
        supporting = 0
        contradicting = 0
        neutral = 0

        for eid in evidence_ids:
            if eid in self.evidence_tracker.evidence_index:
                for cid in self.evidence_tracker.evidence_index[eid]:
                    c = self.evidence_tracker.claims.get(cid)
                    if c:
                        if c.status == "supported":
                            supporting += 1
                        elif c.status == "contradicted":
                            contradicting += 1
                        else:
                            neutral += 1

        # Determine support level
        total = supporting + contradicting + neutral
        if supporting > contradicting and supporting > neutral * 1.5:
            support_level = "supported"
        elif contradicting > supporting and contradicting > neutral * 1.5:
            support_level = "refuted"
        elif supporting > 0:
            support_level = "partially_supported"
        else:
            support_level = "unsubstantiated"

        # Calculate confidence adjustment
        confidence_adjustment = round(
            (supporting - contradicting) / max(1, total) * 0.5, 2
        )
        confidence_adjustment = max(-0.5, min(0.5, confidence_adjustment))

        # Evidence match percentage
        evidence_match = round(supporting / max(1, total) * 100, 2)

        # Generate reasoning
        if supporting > 0 and contradicting == 0:
            reasoning = f"{supporting} piece(s) of evidence support this hypothesis"
        elif contradicting > 0 and supporting == 0:
            reasoning = f"{contradicting} piece(s) of evidence contradict this hypothesis"
        elif supporting > 0 and contradicting > 0:
            reasoning = f"{supporting} supporting and {contradicting} contradicting evidence found"
        else:
            reasoning = "Insufficient evidence to evaluate"

        return {
            "hypothesis_id": hypothesis.id,
            "support_level": support_level,
            "confidence_adjustment": confidence_adjustment,
            "evidence_match": evidence_match,
            "supporting_count": supporting,
            "contradicting_count": contradicting,
            "neutral_count": neutral,
            "total_evidence_considered": total,
            "reasoning": reasoning,
        }


# Singleton
hypothesis_generator = HypothesisGenerator()