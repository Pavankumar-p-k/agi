"""Strategy candidate generation (Phase 12)."""
from __future__ import annotations

from typing import Dict, List, Optional

from core.strategy.models import Strategy, StrategyTag

_BUILD_TOKENS = ("build", "create", "develop", "make", "implement", "add", "app")
_RESEARCH_TOKENS = ("research", "investigate", "study", "analyze", "analyse",
                    "benchmark", "compare", "survey", "explore options")
_REFACTOR_TOKENS = ("refactor", "rewrite", "restructure", "clean up", "cleanup",
                    "migrate")
_EXPLORE_TOKENS = ("explore", "find", "discover", "look for", "identify")


def classify_goal(goal: str) -> str:
    """Classify a natural-language goal into a strategy goal type."""
    text = (goal or "").lower()
    if any(token in text for token in _RESEARCH_TOKENS):
        return "research"
    if any(token in text for token in _REFACTOR_TOKENS):
        return "refactor"
    if any(token in text for token in _EXPLORE_TOKENS):
        return "explore"
    if any(token in text for token in _BUILD_TOKENS):
        return "build"
    # Default: goals that don't clearly match anything still get build plans.
    return "build"


def _strategy(name: str, description: str, goal: str, tags: List[StrategyTag]) -> Strategy:
    return Strategy(name=name, description=description, goal=goal, tags=list(tags))


class StrategyGenerator:
    """Produce a small set of candidate strategies for a goal."""

    def generate(
        self, goal: str, goal_type: Optional[str] = None
    ) -> List[Strategy]:
        gtype = goal_type or classify_goal(goal)
        builders = {
            "build": self._build_candidates,
            "research": self._research_candidates,
            "refactor": self._refactor_candidates,
            "explore": self._explore_candidates,
        }
        generator = builders.get(gtype, self._build_candidates)
        return generator(goal)

    # ── candidate sets ───────────────────────────────────────────────

    def _build_candidates(self, goal: str) -> List[Strategy]:
        return [
            _strategy("MVP-first", "Ship a minimal viable product first.",
                      goal, [StrategyTag.MVP, StrategyTag.SAFE, StrategyTag.FAST]),
            _strategy("Feature-complete", "Build all features before shipping.",
                      goal, [StrategyTag.FEATURE_COMPLETE]),
            _strategy("Quality-first", "Prioritise quality and robustness.",
                      goal, [StrategyTag.QUALITY_FIRST, StrategyTag.THOROUGH]),
            _strategy("Research-driven", "Research best practices before building.",
                      goal, [StrategyTag.RESEARCH_DRIVEN]),
        ]

    def _research_candidates(self, goal: str) -> List[Strategy]:
        return [
            _strategy("Broad-survey", "Survey the whole landscape.",
                      goal, [StrategyTag.BROAD_SURVEY]),
            _strategy("Deep-dive", "Go deep on the most promising area.",
                      goal, [StrategyTag.DEEP_DIVE, StrategyTag.THOROUGH]),
            _strategy("Targeted", "Answer one specific question quickly.",
                      goal, [StrategyTag.TARGETED, StrategyTag.SAFE, StrategyTag.FAST]),
        ]

    def _refactor_candidates(self, goal: str) -> List[Strategy]:
        return [
            _strategy("Minimal-change", "Make the smallest change that works.",
                      goal, [StrategyTag.MINIMAL_CHANGE, StrategyTag.SAFE]),
            _strategy("Incremental", "Improve incrementally over several passes.",
                      goal, [StrategyTag.INCREMENTAL]),
            _strategy("Full-refactor", "Rewrite the whole subsystem.",
                      goal, [StrategyTag.FULL_REFACTOR, StrategyTag.RISKY]),
        ]

    def _explore_candidates(self, goal: str) -> List[Strategy]:
        return [
            _strategy("Exploratory", "Explore freely and see what emerges.",
                      goal, [StrategyTag.EXPLORATORY]),
            _strategy("Comparative", "Compare the leading options.",
                      goal, [StrategyTag.COMPARATIVE]),
            _strategy("Prototype", "Prototype the most promising option.",
                      goal, [StrategyTag.PROTOTYPE, StrategyTag.MVP]),
        ]


async def async_classify_goal(goal: str) -> str:
    return classify_goal(goal)
