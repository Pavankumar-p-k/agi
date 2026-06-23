"""FactSynthesizer — structured research report generation from facts and comparisons."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.research.models import Fact
from core.research.reasoner import (
    Agreement,
    Contradiction,
    FactComparison,
    Gap,
    UniqueClaim,
)

logger = logging.getLogger(__name__)


@dataclass
class ResearchReport:
    """Structured research report with evidence, conflicts, and confidence."""
    topic: str
    sources_consulted: list[str]
    total_facts: int
    summary: str
    evidence_by_source: dict[str, list[str]]
    agreements: list[str]
    conflicts: list[str]
    unique_findings: list[str]
    gaps: list[str]
    overall_confidence: float
    recommendations: list[str]
    generated_at: str = ""


class FactSynthesizer:
    """Generates structured research reports from facts and comparisons.

    Usage:
        synthesizer = FactSynthesizer()
        report = synthesizer.synthesize(
            topic="Competitor pricing analysis",
            facts=[...],
            comparison=reasoner_result,
        )
        print(report.summary)
    """

    def synthesize(self, topic: str,
                   facts: list[Fact],
                   comparison: FactComparison | None = None) -> ResearchReport:
        """Produce a structured ResearchReport from facts and optional comparison."""
        if comparison is None:
            from core.research.reasoner import FactReasoner
            comparison = FactReasoner().analyze(facts)

        sources = sorted(set(f.source_url for f in facts))

        # Evidence grouped by source
        evidence_by_source: dict[str, list[str]] = defaultdict(list)
        for f in facts:
            evidence_by_source[f.source_url].append(f.claim)

        # Generate summary from high-confidence facts across sources
        summary = self._generate_summary(topic, facts, comparison)

        # Agreements as readable strings
        agreements = [a.summary() for a in comparison.agreements]

        # Conflicts as readable strings
        conflicts = [c.summary() for c in comparison.contradictions]

        # Unique findings
        unique_findings = [u.summary() for u in comparison.unique_claims]

        # Gaps
        gaps = [g.summary() for g in comparison.gaps]

        # Overall confidence based on agreement/cross-source ratio
        overall_confidence = self._compute_confidence(facts, comparison)

        # Recommendations
        recommendations = self._generate_recommendations(facts, comparison)

        return ResearchReport(
            topic=topic,
            sources_consulted=sources,
            total_facts=len(facts),
            summary=summary,
            evidence_by_source=dict(evidence_by_source),
            agreements=agreements,
            conflicts=conflicts,
            unique_findings=unique_findings,
            gaps=gaps,
            overall_confidence=round(overall_confidence, 2),
            recommendations=recommendations,
            generated_at=datetime.utcnow().isoformat(),
        )

    def _generate_summary(self, topic: str,
                          facts: list[Fact],
                          comparison: FactComparison) -> str:
        """Generate a human-readable summary from facts and comparisons."""
        if not facts:
            return f"No facts found for '{topic}'."

        parts: list[str] = [
            f"Research on '{topic}' covered {len(facts)} facts from {len(comparison.sources_analyzed)} sources."
        ]

        # Top high-confidence facts (by agreement count)
        if comparison.agreements:
            top_agreements = sorted(comparison.agreements,
                                    key=lambda a: len(a.facts), reverse=True)[:2]
            for a in top_agreements:
                parts.append(f"Confirmed: {a.summary()}")

        # Contradictions
        if comparison.contradictions:
            top_conflicts = sorted(comparison.contradictions,
                                   key=lambda c: len(c.facts), reverse=True)[:2]
            for c in top_conflicts:
                parts.append(f"Conflict detected: {c.summary()}")

        # Unique claims worth noting
        high_conf_unique = [u for u in comparison.unique_claims
                            if u.fact.confidence > 0.7]
        if high_conf_unique:
            parts.append(f"Notable unique finding: {high_conf_unique[0].summary()}")

        # Source diversity
        if len(comparison.sources_analyzed) >= 2:
            parts.append(
                f"Information corroborated across {len(comparison.sources_analyzed)} sources."
            )
        else:
            parts.append(
                "Information from a single source — further verification recommended."
            )

        return " ".join(parts)

    def _compute_confidence(self, facts: list[Fact],
                            comparison: FactComparison) -> float:
        """Compute overall confidence based on evidence quality."""
        if not facts:
            return 0.0

        # Base: average fact confidence
        avg_confidence = sum(f.confidence for f in facts) / len(facts)

        # Boost for cross-source corroboration
        cross_source_ratio = 0.0
        if comparison.agreements:
            multi_source = sum(1 for a in comparison.agreements
                               if len(set(f.source_url for f in a.facts)) >= 2)
            cross_source_ratio = multi_source / len(comparison.agreements)

        cross_source_bonus = cross_source_ratio * 0.2

        # Penalty for unresolved contradictions
        contradiction_penalty = len(comparison.contradictions) * 0.1

        # Penalty for single-source dependency
        single_source_penalty = 0.0
        if len(comparison.sources_analyzed) <= 1:
            single_source_penalty = 0.15

        score = avg_confidence + cross_source_bonus - contradiction_penalty - single_source_penalty
        return max(0.0, min(1.0, score))

    def _generate_recommendations(self, facts: list[Fact],
                                   comparison: FactComparison) -> list[str]:
        """Generate action-oriented recommendations from the analysis."""
        recommendations: list[str] = []

        if comparison.contradictions:
            recommendations.append(
                "Resolve contradictions by consulting primary/official sources "
                f"for: {', '.join(c.entity for c in comparison.contradictions[:3])}"
            )

        if comparison.gaps:
            recommendations.append(
                f"Address {len(comparison.gaps)} knowledge gaps "
                "with targeted follow-up research."
            )

        if len(comparison.sources_analyzed) <= 1:
            recommendations.append(
                "Corroborate findings with additional independent sources."
            )

        if len(comparison.sources_analyzed) >= 3 and not comparison.contradictions:
            recommendations.append(
                "High confidence in findings — proceed with decision-making."
            )

        if comparison.unique_claims:
            high_conf_unique = [u for u in comparison.unique_claims
                                if u.fact.confidence > 0.7]
            if high_conf_unique:
                recommendations.append(
                    f"Verify unique high-confidence claim: {high_conf_unique[0].summary()}"
                )

        if not recommendations:
            recommendations.append(
                "Insufficient data for recommendations — more research needed."
            )

        return recommendations
