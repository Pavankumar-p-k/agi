"""GapDetector — identifies missing information and recommends next research steps."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from core.research.models import Fact
from core.research.planner import GoalStatus, ResearchPlan, ResearchGoal

logger = logging.getLogger(__name__)


@dataclass
class GapAnalysis:
    """Evaluation of evidence gaps across a research plan."""
    plan_id: str
    goals_answered: list[str]
    goals_with_gaps: list[str]
    goals_contradicted: list[str]
    follow_up_queries: list[str]
    sufficient: bool
    recommendation: str
    confidence: float
    details: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        return (f"GapAnalysis: {len(self.goals_answered)} answered, "
                f"{len(self.goals_with_gaps)} gaps, "
                f"{len(self.goals_contradicted)} contradicted | "
                f"Sufficient: {self.sufficient} | "
                f"Confidence: {self.confidence:.2f} | "
                f"Recommendation: {self.recommendation}")


class GapDetector:
    """Analyzes collected evidence against research goals and identifies gaps.

    Determines when:
    - A goal has sufficient evidence (can be marked answered)
    - A goal needs more evidence (generate follow-up queries)
    - A contradiction needs resolution (flag for deeper research)
    - Research should stop (all goals met or max iterations reached)

    Usage:
        detector = GapDetector()
        analysis = detector.analyze(plan, facts)
        if analysis.sufficient:
            # synthesize final report
        else:
            new_queries = analysis.follow_up_queries
            # continue researching
    """

    # Thresholds (configurable)
    MIN_FACTS_PER_GOAL: int = 3
    MIN_CONFIDENCE: float = 0.4
    MIN_SOURCES: int = 2
    MAX_GAP_ITERATIONS: int = 2

    def analyze(self, plan: ResearchPlan,
                facts: list[Fact] | list[dict]) -> GapAnalysis:
        """Analyze evidence gaps in a research plan."""
        # Convert Fact objects to dicts if needed
        fact_dicts = self._to_dicts(facts)

        answered: list[str] = []
        gaps: list[str] = []
        contradicted: list[str] = []
        follow_up: list[str] = []

        for goal in plan.goals:
            goal_facts = [f for f in fact_dicts
                          if self._fact_matches_goal(f, goal)]
            status = self._evaluate_goal_sufficiency(goal, goal_facts,
                                                     plan.iteration)

            if status == "answered":
                answered.append(goal.question[:80])
            elif status == "contradicted":
                contradicted.append(goal.question[:80])
                follow_up.append(
                    f"Resolve contradiction: {goal.question[:100]}")
            elif status == "gap":
                gaps.append(goal.question[:80])
                # Generate follow-up queries
                new_queries = self._generate_follow_up(goal, goal_facts,
                                                       plan.iteration)
                follow_up.extend(new_queries)

        # Overall assessment
        total = len(plan.goals)
        answered_count = len(answered)
        sufficient = (answered_count / total >= 0.8) if total > 0 else False

        # Confidence
        all_confidences = [
            f.get("confidence", 0.5) for f in fact_dicts
            if isinstance(f.get("confidence"), (int, float))
        ]
        avg_conf = (sum(all_confidences) / len(all_confidences)
                    if all_confidences else 0.0)
        source_count = len(set(
            f.get("source_url", "") for f in fact_dicts if f.get("source_url")
        ))

        # Recommendation
        if sufficient:
            recommendation = "Evidence sufficient — proceed to synthesis."
        elif len(gaps) > 0:
            recommendation = (f"Follow up on {len(gaps)} gaps "
                              f"with {len(follow_up)} new queries.")
        elif len(contradicted) > 0:
            recommendation = (f"Resolve {len(contradicted)} contradictions "
                              f"before continuing.")
        else:
            recommendation = "Continue research — insufficient evidence."

        return GapAnalysis(
            plan_id=plan.plan_id,
            goals_answered=answered,
            goals_with_gaps=gaps,
            goals_contradicted=contradicted,
            follow_up_queries=follow_up,
            sufficient=sufficient,
            recommendation=recommendation,
            confidence=round(avg_conf, 2),
            details={
                "total_goals": total,
                "total_facts": len(fact_dicts),
                "sources_consulted": source_count,
                "iteration": plan.iteration,
            },
        )

    def _evaluate_goal_sufficiency(self, goal: ResearchGoal,
                                    facts: list[dict],
                                    iteration: int) -> str:
        """Determine if a goal has sufficient evidence."""
        if not facts:
            if iteration >= self.MAX_GAP_ITERATIONS:
                return "gap"
            return "gap"

        # Check contradictions FIRST (can be detected with 2 facts)
        from core.research.linker import Linker
        from core.research.models import Fact
        linker = Linker()
        fact_objects = []
        for f in facts[:15]:
            try:
                fact_objects.append(Fact(
                    fact_id=f.get("fact_id", ""),
                    source_url=f.get("source_url", ""),
                    claim=f.get("claim", ""),
                ))
            except Exception:
                continue

        contradiction_count = 0
        for i in range(len(fact_objects)):
            for j in range(i + 1, len(fact_objects)):
                rel = linker.classify_relationship(fact_objects[i],
                                                    fact_objects[j])
                if rel == "CONTRADICTS":
                    contradiction_count += 1

        if contradiction_count > 0:
            return "contradicted"

        # Check fact count
        if len(facts) < self.MIN_FACTS_PER_GOAL:
            return "gap"

        # Check confidence
        confidences = [f.get("confidence", 0.5) for f in facts
                       if isinstance(f.get("confidence"), (int, float))]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        if avg_conf < self.MIN_CONFIDENCE:
            return "gap"

        # Check multi-source
        sources = set(f.get("source_url", "") for f in facts
                      if f.get("source_url"))
        if len(sources) < self.MIN_SOURCES:
            return "gap"

        return "answered"

    def _generate_follow_up(self, goal: ResearchGoal,
                             facts: list[dict],
                             iteration: int) -> list[str]:
        """Generate follow-up search queries for a gap goal."""
        queries: list[str] = []

        if iteration == 0:
            queries.append(f"detailed information about {goal.question[:80]}")
        elif iteration == 1:
            # Try to find alternative sources
            queries.append(f"{goal.question[:60]} review comparison")
        else:
            queries.append(f"latest {goal.question[:60]}")

        # Add entity-specific queries
        for f in facts[:3]:
            claim = f.get("claim", "")
            entities = re.findall(r'\b[A-Z][a-zA-Z]+\b', claim)
            for e in entities[:2]:
                if len(e) > 2 and e.lower() not in ("the", "this", "that"):
                    queries.append(f"{e} {goal.question[:50]}")

        return queries[:4]

    def _fact_matches_goal(self, fact: dict, goal: ResearchGoal) -> bool:
        """Check if a fact dict is relevant to a goal."""
        from core.research.planner import ResearchPlanner
        # Reuse the planner's fact-goal matching
        return ResearchPlanner()._fact_matches_goal(fact, goal)

    def _to_dicts(self, facts: list[Fact] | list[dict]) -> list[dict]:
        """Normalize facts to dict format."""
        result: list[dict] = []
        for f in facts:
            if isinstance(f, dict):
                result.append(f)
            else:
                result.append({
                    "fact_id": f.fact_id,
                    "source_url": f.source_url,
                    "claim": f.claim,
                    "confidence": f.confidence,
                    "category": f.category,
                    "tags": f.tags,
                })
        return result
