"""EvidenceTracker — links facts to research goals and hypotheses, tracks coverage."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from core.research.models import Fact

logger = logging.getLogger(__name__)


@dataclass
class GoalCoverage:
    """Coverage assessment for a single research goal."""
    goal_id: str
    goal_question: str
    total_facts: int
    unique_sources: int
    average_confidence: float
    contradictions: int
    gaps: list[str]
    sufficient: bool


@dataclass
class ResearchCoverage:
    """Full coverage assessment across all goals and hypotheses."""
    total_facts: int
    total_goals: int
    covered_goals: int
    gap_goals: int
    overall_confidence: float
    multi_source_ratio: float
    goals: list[GoalCoverage] = field(default_factory=list)


class EvidenceTracker:
    """Tracks which facts map to which research goals and hypotheses.

    Maintains a bidirectional mapping:
    - fact_id → [goal_ids]
    - goal_id → [fact_ids]

    Usage:
        tracker = EvidenceTracker()
        tracker.link_fact_to_goal(fact, goal_id)
        coverage = tracker.get_coverage(goal_id)
        report = tracker.summarize_coverage()
    """

    def __init__(self):
        self._fact_to_goals: dict[str, set[str]] = defaultdict(set)
        self._goal_to_facts: dict[str, set[str]] = defaultdict(set)
        self._goal_questions: dict[str, str] = {}
        self._all_facts: dict[str, Fact] = {}
        self._hypothesis_links: dict[str, set[str]] = defaultdict(set)

    def register_goal(self, goal_id: str, question: str) -> None:
        """Register a research goal for tracking."""
        self._goal_questions[goal_id] = question

    def link_fact_to_goal(self, fact: Fact, goal_id: str) -> None:
        """Link a fact to a research goal."""
        self._fact_to_goals[fact.fact_id].add(goal_id)
        self._goal_to_facts[goal_id].add(fact.fact_id)
        self._all_facts[fact.fact_id] = fact

    def link_fact_to_hypothesis(self, fact: Fact,
                                 hypothesis_id: str) -> None:
        """Link a fact to a hypothesis."""
        self._hypothesis_links[hypothesis_id].add(fact.fact_id)
        self._all_facts[fact.fact_id] = fact

    def get_facts_for_goal(self, goal_id: str) -> list[Fact]:
        """Get all facts linked to a goal."""
        fact_ids = self._goal_to_facts.get(goal_id, set())
        return [self._all_facts[fid] for fid in fact_ids
                if fid in self._all_facts]

    def get_goals_for_fact(self, fact_id: str) -> list[str]:
        """Get all goals linked to a fact."""
        return list(self._fact_to_goals.get(fact_id, set()))

    def get_coverage(self, goal_id: str) -> GoalCoverage:
        """Get coverage assessment for a single goal."""
        facts = self.get_facts_for_goal(goal_id)
        question = self._goal_questions.get(goal_id, "")

        if not facts:
            return GoalCoverage(
                goal_id=goal_id,
                goal_question=question,
                total_facts=0,
                unique_sources=0,
                average_confidence=0.0,
                contradictions=0,
                gaps=["No evidence collected"],
                sufficient=False,
            )

        sources = set(f.source_url for f in facts if f.source_url)
        confidences = [f.confidence for f in facts]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        # Detect contradictions
        from core.research.linker import Linker
        linker = Linker()
        contradictions = 0
        for i in range(len(facts)):
            for j in range(i + 1, len(facts)):
                rel = linker.classify_relationship(facts[i], facts[j])
                if rel == "CONTRADICTS":
                    contradictions += 1

        # Identify gaps
        gaps: list[str] = []
        if len(sources) < 2:
            gaps.append("Only single source — corroboration needed")
        if avg_conf < 0.5:
            gaps.append("Low average confidence")
        if contradictions > 0:
            gaps.append(f"{contradictions} contradiction(s) detected")

        sufficient = (len(facts) >= 3 and len(sources) >= 2
                      and avg_conf >= 0.5 and contradictions == 0)

        return GoalCoverage(
            goal_id=goal_id,
            goal_question=question,
            total_facts=len(facts),
            unique_sources=len(sources),
            average_confidence=round(avg_conf, 2),
            contradictions=contradictions,
            gaps=gaps,
            sufficient=sufficient,
        )

    def summarize_coverage(self) -> ResearchCoverage:
        """Produce a full coverage summary across all goals."""
        all_goals = list(self._goal_questions.keys())
        if not all_goals:
            return ResearchCoverage(
                total_facts=len(self._all_facts),
                total_goals=0,
                covered_goals=0,
                gap_goals=0,
                overall_confidence=0.0,
                multi_source_ratio=0.0,
                goals=[],
            )

        goal_coverages = [self.get_coverage(gid) for gid in all_goals]
        covered = sum(1 for gc in goal_coverages if gc.sufficient)
        gaps = sum(1 for gc in goal_coverages if not gc.sufficient)

        overall_conf = (
            sum(gc.average_confidence for gc in goal_coverages)
            / len(goal_coverages)
        )

        multi_source_goals = sum(
            1 for gc in goal_coverages if gc.unique_sources >= 2
        )
        multi_source_ratio = (
            multi_source_goals / len(goal_coverages)
            if goal_coverages else 0.0
        )

        return ResearchCoverage(
            total_facts=len(self._all_facts),
            total_goals=len(all_goals),
            covered_goals=covered,
            gap_goals=gaps,
            overall_confidence=round(overall_conf, 2),
            multi_source_ratio=round(multi_source_ratio, 2),
            goals=goal_coverages,
        )

    def clear(self) -> None:
        """Clear all tracking data."""
        self._fact_to_goals.clear()
        self._goal_to_facts.clear()
        self._goal_questions.clear()
        self._all_facts.clear()
        self._hypothesis_links.clear()
