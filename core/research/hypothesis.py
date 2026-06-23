"""HypothesisManager — claim-level hypothesis tracking with evidence evaluation."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.research.models import Fact

logger = logging.getLogger(__name__)


@dataclass
class Hypothesis:
    """A claim-level hypothesis with supporting and contradicting evidence."""
    hypothesis_id: str
    claim: str
    supporting_facts: list[Fact] = field(default_factory=list)
    contradicting_facts: list[Fact] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "unverified"  # unverified, plausible, likely, confirmed, rejected
    gaps: list[str] = field(default_factory=list)
    note: str = ""

    def summary(self) -> str:
        return (f"[{self.status}] {self.claim[:80]} "
                f"(conf={self.confidence:.2f}, "
                f"{len(self.supporting_facts)} for, "
                f"{len(self.contradicting_facts)} against)")

    def add_support(self, fact: Fact) -> None:
        self.supporting_facts.append(fact)
        self._recompute()

    def add_contradiction(self, fact: Fact) -> None:
        self.contradicting_facts.append(fact)
        self._recompute()

    def _recompute(self) -> None:
        sup = len(self.supporting_facts)
        con = len(self.contradicting_facts)
        total = sup + con

        if total == 0:
            self.confidence = 0.0
            self.status = "unverified"
            return

        # Base: fraction of facts that support
        base_confidence = sup / total if total > 0 else 0.0

        # Multi-source bonus
        all_facts = self.supporting_facts + self.contradicting_facts
        sources = set(f.source_url for f in all_facts)
        source_bonus = min(0.2, len(sources) * 0.05)

        # Confidence bonus from fact confidence scores
        avg_fact_conf = sum(f.confidence for f in all_facts) / total
        quality_bonus = avg_fact_conf * 0.15

        self.confidence = min(1.0, base_confidence + source_bonus + quality_bonus)

        # Status
        if con > sup:
            self.status = "rejected"
        elif self.confidence >= 0.8:
            self.status = "confirmed"
        elif self.confidence >= 0.6:
            self.status = "likely"
        elif self.confidence >= 0.3:
            self.status = "plausible"
        else:
            self.status = "unverified"


class HypothesisManager:
    """Manages multiple hypotheses and links facts to them.

    Usage:
        manager = HypothesisManager()
        h = manager.create_hypothesis("Company X costs $10/month")
        manager.add_evidence(h.hypothesis_id, fact_a)  # supporting
        manager.add_evidence(h.hypothesis_id, fact_b)  # contradicting
        print(h.summary())
    """

    def __init__(self):
        self._hypotheses: dict[str, Hypothesis] = {}

    def create_hypothesis(self, claim: str) -> Hypothesis:
        """Create a new hypothesis from a claim."""
        h = Hypothesis(
            hypothesis_id=f"hyp_{uuid.uuid4().hex[:12]}",
            claim=claim,
        )
        self._hypotheses[h.hypothesis_id] = h
        return h

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        return self._hypotheses.get(hypothesis_id)

    def add_evidence(self, hypothesis_id: str, fact: Fact,
                     relationship: str | None = None) -> None:
        """Add a fact to a hypothesis, auto-classifying the relationship."""
        h = self._hypotheses.get(hypothesis_id)
        if h is None:
            return

        if relationship == "contradicts":
            h.add_contradiction(fact)
        elif relationship == "supports":
            h.add_support(fact)
        else:
            # Auto-classify using linker
            from core.research.linker import Linker
            linker = Linker()
            dummy_fact = Fact(
                fact_id="hypothesis_claim",
                source_url="",
                claim=h.claim,
                confidence=1.0,
            )
            rel = linker.classify_relationship(fact, dummy_fact)
            if rel == "CONTRADICTS":
                h.add_contradiction(fact)
            else:
                h.add_support(fact)

    def add_evidence_batch(self, hypothesis_id: str,
                           facts: list[Fact]) -> None:
        """Add multiple facts to a hypothesis."""
        for f in facts:
            self.add_evidence(hypothesis_id, f)

    def get_all(self) -> list[Hypothesis]:
        return list(self._hypotheses.values())

    def get_confirmed(self) -> list[Hypothesis]:
        return [h for h in self._hypotheses.values()
                if h.status in ("confirmed", "likely")]

    def get_rejected(self) -> list[Hypothesis]:
        return [h for h in self._hypotheses.values()
                if h.status == "rejected"]

    def evaluate_all(self) -> dict[str, Any]:
        """Produce an evaluation summary of all hypotheses."""
        all_h = self.get_all()
        return {
            "total": len(all_h),
            "confirmed": len(self.get_confirmed()),
            "rejected": len(self.get_rejected()),
            "unverified": sum(1 for h in all_h if h.status == "unverified"),
            "average_confidence": (
                round(sum(h.confidence for h in all_h) / len(all_h), 2)
                if all_h else 0.0
            ),
            "hypotheses": [
                {
                    "id": h.hypothesis_id[:8],
                    "claim": h.claim[:80],
                    "status": h.status,
                    "confidence": round(h.confidence, 2),
                    "supporting": len(h.supporting_facts),
                    "contradicting": len(h.contradicting_facts),
                }
                for h in all_h
            ],
        }
