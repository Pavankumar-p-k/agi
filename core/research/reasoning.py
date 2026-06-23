"""ReasoningEngine — belief-driven research with hypothesis generation, evidence revision, and conclusion synthesis.

This is the core of Phase 7.5. It transforms research from:
  Question → Collect → Report
to:
  Question → Hypotheses → Collect → Challenge → Revise → Conclude

Key capabilities:
- Belief state management with confidence tracking
- Evidence-driven belief revision (simplified Bayesian update)
- Counter-hypothesis generation to actively challenge beliefs
- Confidence-aware conclusion synthesis
- Revision history for traceability
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.research.models import Fact

logger = logging.getLogger(__name__)


# ── Evidence ────────────────────────────────────────────────────────────


@dataclass
class EvidenceItem:
    """A single piece of evidence for or against a belief."""
    evidence_id: str
    fact: Fact
    direction: str  # "supports" or "contradicts"
    weight: float = 1.0  # Strength of this evidence
    timestamp: str = ""

    def summary(self) -> str:
        arrow = "+" if self.direction == "supports" else "−"
        return f"{arrow}[{self.weight:.1f}] {self.fact.claim[:80]} (src={self.fact.source_url[:40]})"


# ── Belief ──────────────────────────────────────────────────────────────


@dataclass
class BeliefRevision:
    """A record of a belief being revised."""
    revision_id: str
    previous_confidence: float
    new_confidence: float
    reason: str  # "new_evidence", "counter_evidence", "challenge"
    evidence_ids: list[str]
    timestamp: str


@dataclass
class Belief:
    """A single belief with supporting and contradicting evidence.

    Confidence is updated via a simplified Bayesian approach:
      P(H|E) ∝ P(H) * P(E|H) / P(E)

    Simplified for deterministic use as:
      new_conf = (prior * total_weight + sum(support_weight)) / (total_weight + sum(all_weights))
    """
    belief_id: str
    claim: str
    confidence: float = 0.5  # Prior confidence
    status: str = "unverified"  # unverified, plausible, likely, confirmed, rejected, revised
    evidence: list[EvidenceItem] = field(default_factory=list)
    revisions: list[BeliefRevision] = field(default_factory=list)
    counter_hypothesis_id: str | None = None
    note: str = ""

    def supporting_evidence(self) -> list[EvidenceItem]:
        return [e for e in self.evidence if e.direction == "supports"]

    def contradicting_evidence(self) -> list[EvidenceItem]:
        return [e for e in self.evidence if e.direction == "contradicts"]

    def total_weight(self) -> float:
        return sum(e.weight for e in self.evidence)

    def support_weight(self) -> float:
        return sum(e.weight for e in self.evidence if e.direction == "supports")

    def source_count(self) -> int:
        return len(set(e.fact.source_url for e in self.evidence if e.fact.source_url))

    def add_evidence(self, fact: Fact, direction: str,
                     weight: float | None = None) -> EvidenceItem:
        """Add evidence and update confidence."""
        if weight is None:
            weight = fact.confidence

        item = EvidenceItem(
            evidence_id=f"ev_{uuid.uuid4().hex[:12]}",
            fact=fact,
            direction=direction,
            weight=weight,
            timestamp=datetime.utcnow().isoformat(),
        )
        self.evidence.append(item)
        self._revise_confidence(reason=f"new_{direction}_evidence",
                                evidence_ids=[item.evidence_id])
        return item

    def _revise_confidence(self, reason: str,
                           evidence_ids: list[str]) -> None:
        """Recompute confidence using simplified Bayesian update."""
        prior = self.confidence
        total_w = self.total_weight()
        support_w = self.support_weight()

        if total_w == 0:
            new_confidence = prior
        else:
            # Bayesian-inspired: prior weighted by total evidence, shifted by support ratio
            evidence_strength = support_w / total_w  # fraction of weight supporting
            new_confidence = (prior * 0.3 + evidence_strength * 0.7)

            # Multi-source bonus
            sources = self.source_count()
            if sources >= 2:
                new_confidence = min(1.0, new_confidence + 0.05 * min(sources, 4))

        new_confidence = max(0.01, min(0.99, new_confidence))
        self.confidence = round(new_confidence, 3)

        # Record revision
        self.revisions.append(BeliefRevision(
            revision_id=f"rev_{uuid.uuid4().hex[:8]}",
            previous_confidence=prior,
            new_confidence=self.confidence,
            reason=reason,
            evidence_ids=evidence_ids,
            timestamp=datetime.utcnow().isoformat(),
        ))

        # Update status
        self._update_status()

    def _update_status(self) -> None:
        sup = len(self.supporting_evidence())
        con = len(self.contradicting_evidence())

        if con > sup:
            self.status = "rejected"
        elif self.confidence >= 0.8:
            if len(self.revisions) > 1:
                self.status = "revised"  # Was revised then confirmed
            else:
                self.status = "confirmed"
        elif self.confidence >= 0.6:
            self.status = "likely"
        elif self.confidence >= 0.3:
            self.status = "plausible"
        else:
            self.status = "unverified"

        if len(self.revisions) > 1 and self.status not in ("rejected", "revised"):
            self.status = "revised"

    def summary(self) -> str:
        return (f"[{self.status}] {self.claim[:80]} "
                f"(conf={self.confidence:.2f}, "
                f"{len(self.supporting_evidence())}+/{len(self.contradicting_evidence())}-, "
                f"{self.source_count()} sources, "
                f"{len(self.revisions)} revisions)")


# ── BeliefState ─────────────────────────────────────────────────────────


@dataclass
class BeliefState:
    """The complete set of beliefs about a research topic."""
    topic: str
    beliefs: list[Belief] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def add_belief(self, claim: str, confidence: float = 0.5) -> Belief:
        belief = Belief(
            belief_id=f"blf_{uuid.uuid4().hex[:12]}",
            claim=claim,
            confidence=confidence,
        )
        self.beliefs.append(belief)
        self.updated_at = datetime.utcnow().isoformat()
        return belief

    def get_belief(self, belief_id: str) -> Belief | None:
        for b in self.beliefs:
            if b.belief_id == belief_id:
                return b
        return None

    def find_belief_by_claim(self, claim: str) -> Belief | None:
        for b in self.beliefs:
            if b.claim.lower() == claim.lower():
                return b
        return None

    def find_or_create(self, claim: str) -> Belief:
        existing = self.find_belief_by_claim(claim)
        if existing:
            return existing
        return self.add_belief(claim)

    def confirmed_beliefs(self) -> list[Belief]:
        return [b for b in self.beliefs
                if b.status in ("confirmed", "likely", "revised")]

    def rejected_beliefs(self) -> list[Belief]:
        return [b for b in self.beliefs if b.status == "rejected"]

    def uncertain_beliefs(self) -> list[Belief]:
        return [b for b in self.beliefs
                if b.status in ("unverified", "plausible")]

    def challenged_beliefs(self) -> list[Belief]:
        """Beliefs with conflicting evidence that need resolution."""
        return [b for b in self.beliefs
                if len(b.supporting_evidence()) > 0
                and len(b.contradicting_evidence()) > 0]

    def summary(self) -> str:
        return (f"BeliefState: {len(self.beliefs)} beliefs, "
                f"{len(self.confirmed_beliefs())} confirmed, "
                f"{len(self.rejected_beliefs())} rejected, "
                f"{len(self.challenged_beliefs())} challenged")


# ── Conclusion ──────────────────────────────────────────────────────────


@dataclass
class Conclusion:
    """Final research conclusion with confidence and remaining uncertainties."""
    topic: str
    findings: list[dict]  # [{"claim": ..., "confidence": ..., "status": ..., "sources": ...}]
    uncertainties: list[str]
    overall_confidence: float
    evidence_summary: dict[str, Any]
    recommended_actions: list[str]
    generated_at: str = ""

    def summary(self) -> str:
        confirmed = sum(1 for f in self.findings if f.get("status") in ("confirmed", "likely"))
        return (f"Conclusion on '{self.topic}': "
                f"{confirmed}/{len(self.findings)} findings confirmed, "
                f"conf={self.overall_confidence:.2f}, "
                f"{len(self.uncertainties)} uncertainties")


# ── CounterHypothesis ───────────────────────────────────────────────────


@dataclass
class CounterHypothesis:
    """A counter-hypothesis generated to challenge an existing belief."""
    hypothesis_id: str
    target_belief_id: str
    counter_claim: str
    search_queries: list[str] = field(default_factory=list)
    resolved: bool = False

    def summary(self) -> str:
        return f"Challenge: {self.counter_claim[:80]}"


# ── ReasoningEngine ────────────────────────────────────────────────────


class ReasoningEngine:
    """Belief-driven research with hypothesis generation, evidence revision, and conclusion synthesis.

    This is the highest-level reasoning component in the research pipeline.
    It orchestrates the full loop:

    1. Initialize belief state from question
    2. For each belief, collect evidence
    3. Revise confidence as evidence arrives
    4. Generate counter-hypotheses to challenge uncertain beliefs
    5. Synthesize final conclusion

    Usage:
        engine = ReasoningEngine()
        state = engine.initialize("What does Product Y cost?")
        engine.add_evidence(state, facts)
        counter = engine.generate_challenge(state, state.uncertain_beliefs()[0])
        conclusion = engine.synthesize_conclusion(state)
        print(conclusion.summary())
    """

    def __init__(self):
        self._counter_hypotheses: dict[str, CounterHypothesis] = {}

    # ── Initialization ────────────────────────────────────────────────

    def initialize(self, topic: str) -> BeliefState:
        """Initialize a belief state from a research topic.

        Extracts likely claims from the topic and creates initial beliefs.
        """
        now = datetime.utcnow().isoformat()
        state = BeliefState(
            topic=topic,
            created_at=now,
            updated_at=now,
        )

        # Generate initial beliefs from topic
        initial_claims = self._extract_initial_claims(topic)
        for claim in initial_claims:
            state.add_belief(claim, confidence=0.3)  # Low prior

        return state

    # ── Evidence ──────────────────────────────────────────────────────

    def add_evidence(self, state: BeliefState, facts: list[Fact]) -> list[str]:
        """Add facts as evidence to all relevant beliefs.

        Each fact is compared against the belief's existing evidence to classify
        as support or contradiction. Uses majority voting when a fact
        supports some evidence and contradicts others (multi-source scenario).
        Returns list of belief IDs that were updated.
        """
        from core.research.linker import Linker
        linker = Linker()
        updated: list[str] = []

        for fact in facts:
            for belief in state.beliefs:
                # Check if fact is related to this belief at all
                belief_fact = Fact(
                    fact_id="belief_claim",
                    source_url="",
                    claim=belief.claim,
                    confidence=1.0,
                )
                rel = linker.classify_relationship(fact, belief_fact)
                if rel is None:
                    continue  # Unrelated

                # Compare against all existing evidence, count matches
                supports_count = 0
                contradicts_count = 0

                for existing in belief.evidence:
                    if existing.fact.source_url == fact.source_url:
                        continue  # Same source — skip self-comparison
                    rel_to_existing = linker.classify_relationship(
                        fact, existing.fact
                    )
                    if rel_to_existing == "CONTRADICTS":
                        contradicts_count += 1
                    elif rel_to_existing in ("SUPPORTS", "RELATED_TO"):
                        supports_count += 1

                # Majority voting: contradict if more contradictions than supports
                if contradicts_count > supports_count:
                    direction = "contradicts"
                else:
                    direction = "supports"

                belief.add_evidence(fact, direction)
                updated.append(belief.belief_id)

        state.updated_at = datetime.utcnow().isoformat()
        return list(set(updated))

    def get_evidence_summary(self, state: BeliefState) -> dict[str, Any]:
        """Summarize the evidence landscape."""
        total_evidence = sum(len(b.evidence) for b in state.beliefs)
        total_support = sum(len(b.supporting_evidence()) for b in state.beliefs)
        total_contradict = sum(len(b.contradicting_evidence()) for b in state.beliefs)

        all_sources: set[str] = set()
        for b in state.beliefs:
            for e in b.evidence:
                if e.fact.source_url:
                    all_sources.add(e.fact.source_url)

        return {
            "total_beliefs": len(state.beliefs),
            "total_evidence": total_evidence,
            "total_supporting": total_support,
            "total_contradicting": total_contradict,
            "unique_sources": len(all_sources),
            "average_confidence": round(
                sum(b.confidence for b in state.beliefs) / len(state.beliefs), 2
            ) if state.beliefs else 0.0,
        }

    # ── Challenge ─────────────────────────────────────────────────────

    def generate_challenge(self, state: BeliefState,
                           belief: Belief) -> CounterHypothesis | None:
        """Generate a counter-hypothesis to challenge an uncertain belief.

        The counter-hypothesis claims the opposite of the current belief,
        or identifies a specific unknown that needs resolution.
        """
        if belief.confidence >= 0.8:
            return None  # Already high confidence, no challenge needed

        # Generate counter-claim by negating or questioning
        counter_claim = self._negate_claim(belief.claim)

        # Generate search queries to test the counter-hypothesis
        queries = [
            f"evidence against {belief.claim[:60]}",
            f"alternative to {belief.claim[:60]}",
        ]

        counter = CounterHypothesis(
            hypothesis_id=f"ch_{uuid.uuid4().hex[:12]}",
            target_belief_id=belief.belief_id,
            counter_claim=counter_claim,
            search_queries=queries,
        )
        self._counter_hypotheses[counter.hypothesis_id] = counter
        belief.counter_hypothesis_id = counter.hypothesis_id

        return counter

    def resolve_challenge(self, state: BeliefState,
                          counter: CounterHypothesis,
                          challenge_facts: list[Fact]) -> None:
        """Resolve a counter-hypothesis by adding evidence via the normal pipeline.

        Uses add_evidence with majority-voting to correctly handle
        facts that support some evidence while contradicting others.
        """
        self.add_evidence(state, challenge_facts)
        counter.resolved = True

    # ── Conclusion ────────────────────────────────────────────────────

    def synthesize_conclusion(self, state: BeliefState) -> Conclusion:
        """Produce a structured conclusion from the belief state."""
        findings: list[dict] = []
        uncertainties: list[str] = []

        for belief in state.beliefs:
            sources = list(set(
                e.fact.source_url for e in belief.evidence if e.fact.source_url
            ))
            findings.append({
                "claim": belief.claim,
                "confidence": belief.confidence,
                "status": belief.status,
                "supporting_evidence": len(belief.supporting_evidence()),
                "contradicting_evidence": len(belief.contradicting_evidence()),
                "revisions": len(belief.revisions),
                "sources": sources,
            })

            if belief.status in ("unverified", "plausible"):
                uncertainties.append(
                    f"Insufficient evidence for: {belief.claim[:80]}"
                )
            elif belief.status == "rejected":
                uncertainties.append(
                    f"Claim rejected due to counter-evidence: {belief.claim[:80]}"
                )

        # Overall confidence
        if state.beliefs:
            avg_conf = sum(b.confidence for b in state.beliefs) / len(state.beliefs)
            # Adjust for uncertainty
            uncertainty_penalty = len(uncertainties) * 0.05
            overall = max(0.0, avg_conf - uncertainty_penalty)
        else:
            overall = 0.0

        # Recommended actions
        recommendations: list[str] = []
        if uncertainties:
            recommendations.append(
                f"Resolve {len(uncertainties)} uncertainties with targeted research"
            )
        challenged = state.challenged_beliefs()
        if challenged:
            recommendations.append(
                f"Resolve {len(challenged)} contradictions via counter-hypothesis testing"
            )
        if overall >= 0.7:
            recommendations.append("Sufficient confidence for decision-making")
        else:
            recommendations.append("More evidence needed before conclusions")

        return Conclusion(
            topic=state.topic,
            findings=findings,
            uncertainties=uncertainties,
            overall_confidence=round(overall, 2),
            evidence_summary=self.get_evidence_summary(state),
            recommended_actions=recommendations,
            generated_at=datetime.utcnow().isoformat(),
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _extract_initial_claims(self, topic: str) -> list[str]:
        """Extract initial claims from a research topic."""
        from core.research.linker import Linker
        from core.research.models import Fact
        linker = Linker()
        entities = linker.extract_entities(Fact(
            fact_id="topic", source_url="", claim=topic
        ))

        claims: list[str] = []
        for entity in entities:
            claims.append(f"{entity} is a product/service")
        if not claims:
            claims.append(f"{topic} is a known entity")
        return claims

    def _negate_claim(self, claim: str) -> str:
        """Generate a counter-claim by negating the statement."""
        negation_prefixes = [
            "It is not true that ",
            "The opposite of ",
            "There is evidence against the claim that ",
        ]
        import random
        prefix = negation_prefixes[hash(claim) % len(negation_prefixes)]
        return f"{prefix}{claim}"
