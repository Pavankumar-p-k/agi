"""StrategyGenerator — produces candidate strategies for a given goal.

Deterministic. Uses templates based on goal type and heuristics
to generate a small set of distinct approaches.

Strategy encoding per goal type:
  build:
    MVP-first, Feature-complete, Quality-first, Research-driven
  research:
    Broad-survey, Deep-dive, Targeted, Iterative
  refactor:
    Minimal-change, Full-refactor, Incremental, Safe
  explore:
    Quick-scan, Comprehensive, Follow-leads
"""

from __future__ import annotations

import logging
from typing import Any

from core.strategy.models import Strategy, StrategyTag

logger = logging.getLogger(__name__)

# Templates map (goal_type, appetite) → strategy parameters
_STRATEGY_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "build": [
        {
            "name": "MVP-first",
            "description": "Build the smallest useful feature set first, then iterate.",
            "tags": [StrategyTag.MVP, StrategyTag.SAFE, StrategyTag.ITERATIVE],
        },
        {
            "name": "Feature-complete",
            "description": "Build all planned features before shipping.",
            "tags": [StrategyTag.FEATURE_COMPLETE, StrategyTag.AMBITIOUS],
        },
        {
            "name": "Quality-first",
            "description": "Fewer features, higher quality — tests, docs, robustness.",
            "tags": [StrategyTag.QUALITY_FIRST, StrategyTag.SAFE],
        },
        {
            "name": "Research-driven",
            "description": "Extensive research phase before implementation begins.",
            "tags": [StrategyTag.RESEARCH_DRIVEN, StrategyTag.SAFE],
        },
    ],
    "research": [
        {
            "name": "Broad-survey",
            "description": "Cover many sources quickly to map the landscape.",
            "tags": [StrategyTag.MVP, StrategyTag.ITERATIVE],
        },
        {
            "name": "Deep-dive",
            "description": "Fewer sources but thorough analysis of each.",
            "tags": [StrategyTag.FEATURE_COMPLETE, StrategyTag.QUALITY_FIRST],
        },
        {
            "name": "Targeted",
            "description": "Focus on specific questions with high-confidence sources.",
            "tags": [StrategyTag.SAFE],
        },
    ],
    "refactor": [
        {
            "name": "Minimal-change",
            "description": "Smallest safe change that achieves the goal.",
            "tags": [StrategyTag.SAFE, StrategyTag.MVP],
        },
        {
            "name": "Incremental",
            "description": "Multiple small refactors over time.",
            "tags": [StrategyTag.ITERATIVE, StrategyTag.SAFE],
        },
        {
            "name": "Full-refactor",
            "description": "Rewrite or restructure comprehensively.",
            "tags": [StrategyTag.AMBITIOUS, StrategyTag.FEATURE_COMPLETE],
        },
    ],
    "explore": [
        {
            "name": "Quick-scan",
            "description": "Fast overview of available information.",
            "tags": [StrategyTag.MVP],
        },
        {
            "name": "Comprehensive",
            "description": "Thorough exploration of all paths.",
            "tags": [StrategyTag.FEATURE_COMPLETE],
        },
        {
            "name": "Follow-leads",
            "description": "Start broad, then follow promising leads deeper.",
            "tags": [StrategyTag.ITERATIVE],
        },
    ],
}


def classify_goal(goal: str) -> str:
    """Classify a goal into a type for strategy generation."""
    goal_lower = goal.lower()
    if any(kw in goal_lower for kw in ("build ", "create ", "develop ", "implement ")):
        return "build"
    if any(kw in goal_lower for kw in ("research ", "investigate ", "study ", "learn ")):
        return "research"
    if any(kw in goal_lower for kw in ("refactor ", "rewrite ", "restructure ", "migrate ")):
        return "refactor"
    if any(kw in goal_lower for kw in ("explore ", "find ", "discover ", "survey ")):
        return "explore"
    return "build"  # default


class StrategyGenerator:
    """Generates candidate strategies for a goal."""

    def generate(self, goal: str, goal_type: str | None = None) -> list[Strategy]:
        """Produce candidate strategies for the given goal.

        Args:
            goal: The user's goal.
            goal_type: Override goal classification (optional).

        Returns:
            List of distinct Strategy objects.
        """
        gtype = goal_type or classify_goal(goal)
        templates = _STRATEGY_TEMPLATES.get(gtype, _STRATEGY_TEMPLATES["build"])

        strategies: list[Strategy] = []
        seen_names: set[str] = set()
        for t in templates:
            name = t["name"]
            if name not in seen_names:
                seen_names.add(name)
                strategies.append(Strategy(
                    name=name,
                    description=t["description"],
                    goal=goal,
                    tags=list(t["tags"]),
                ))

        logger.info("StrategyGenerator: generated %d strategies for goal_type=%s",
                     len(strategies), gtype)
        return strategies
