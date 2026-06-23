"""ImprovementDetector — scans KnowledgeStore for patterns that suggest behavior changes.
"""

from __future__ import annotations

import logging
import uuid

from core.improvement.models import ImprovementProposal, KnobCategory
from core.long_term_memory.models import KnowledgeQuery
from core.long_term_memory.store import KnowledgeStore

logger = logging.getLogger(__name__)

_MIN_CONFIDENCE_TO_PROPOSE = 0.6


class ImprovementDetector:
    """Scans knowledge and experience stores for improvement opportunities."""

    def __init__(self, store: KnowledgeStore | None = None):
        self._store = store or KnowledgeStore()

    def detect_all(self) -> list[ImprovementProposal]:
        proposals: list[ImprovementProposal] = []
        proposals.extend(self._detect_domain_performance())
        proposals.extend(self._detect_failure_patterns())
        proposals.extend(self._detect_tool_patterns())
        proposals.extend(self._detect_principle_gaps())
        return self._deduplicate(proposals)

    def _detect_domain_performance(self) -> list[ImprovementProposal]:
        proposals: list[ImprovementProposal] = []
        domain_warnings = self._store.query_knowledge(
            KnowledgeQuery(category="warning", tag="domain_failure",
                           min_confidence=_MIN_CONFIDENCE_TO_PROPOSE),
        )
        for item in domain_warnings:
            domain = "unknown"
            for t in item.tags:
                if t not in ("domain_failure", "warning"):
                    domain = t
            proposals.append(ImprovementProposal(
                proposal_id=f"prop_{uuid.uuid4().hex[:12]}",
                reason=f"Domain '{domain}' has low success rate (confidence={item.confidence:.0%})",
                category=KnobCategory.PLANNER,
                confidence=item.confidence,
                source_knowledge_ids=[item.knowledge_id],
                suggested_change=f"Increase planner safeguards for '{domain}' tasks",
            ))
        return proposals

    def _detect_failure_patterns(self) -> list[ImprovementProposal]:
        proposals: list[ImprovementProposal] = []
        principles = self._store.query_knowledge(
            KnowledgeQuery(category="principle", min_confidence=_MIN_CONFIDENCE_TO_PROPOSE),
        )
        for item in principles:
            if "error" in item.claim.lower() and "fail" in item.claim.lower():
                proposals.append(ImprovementProposal(
                    proposal_id=f"prop_{uuid.uuid4().hex[:12]}",
                    reason=f"Errors correlate with failures: {item.claim}",
                    category=KnobCategory.CODING,
                    confidence=item.confidence,
                    source_knowledge_ids=[item.knowledge_id],
                    suggested_change="Enable coding.simulation_required to catch errors before refactors",
                ))
        return proposals

    def _detect_tool_patterns(self) -> list[ImprovementProposal]:
        proposals: list[ImprovementProposal] = []
        warnings = self._store.query_knowledge(
            KnowledgeQuery(category="warning", min_confidence=_MIN_CONFIDENCE_TO_PROPOSE),
        )
        for item in warnings:
            if "failure_pattern" in item.tags:
                proposals.append(ImprovementProposal(
                    proposal_id=f"prop_{uuid.uuid4().hex[:12]}",
                    reason=f"Failure pattern: {item.claim[:80]}",
                    category=KnobCategory.CODING,
                    confidence=item.confidence,
                    source_knowledge_ids=[item.knowledge_id],
                    suggested_change="Review coding.safety_threshold for higher caution",
                ))
        return proposals

    def _detect_principle_gaps(self) -> list[ImprovementProposal]:
        proposals: list[ImprovementProposal] = []
        principles = self._store.query_knowledge(
            KnowledgeQuery(category="principle", min_confidence=_MIN_CONFIDENCE_TO_PROPOSE),
        )
        for item in principles:
            if item.confidence >= 0.8 and item.evidence_count >= 5:
                proposals.append(ImprovementProposal(
                    proposal_id=f"prop_{uuid.uuid4().hex[:12]}",
                    reason=f"High-confidence principle (conf={item.confidence:.0%}, ev={item.evidence_count})",
                    category=KnobCategory.PLANNER,
                    confidence=item.confidence,
                    source_knowledge_ids=[item.knowledge_id],
                    suggested_change=f"Inject into planner: {item.claim[:60]}",
                ))
        return proposals

    @staticmethod
    def _deduplicate(proposals: list[ImprovementProposal]) -> list[ImprovementProposal]:
        best: dict[str, ImprovementProposal] = {}
        for p in proposals:
            cat = p.category.value
            if cat not in best or p.confidence > best[cat].confidence:
                best[cat] = p
        return list(best.values())
