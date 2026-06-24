"""Strategy definitions and multi-plan generation for comparative planning.

Each strategy represents a different architectural approach to a goal.
The StrategyGenerator produces N candidate plan trees, one per strategy,
which can then be scored and compared by ComparativeScorer.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.planner.decomposer import GoalDecomposer, _find_features
from core.planner.models import SubGoal

logger = logging.getLogger(__name__)

# ── Strategy definitions ─────────────────────────────────────────────────────

STRATEGY_REGISTRY: dict[str, dict[str, Any]] = {
    "flutter": {
        "label": "Flutter",
        "description": "Cross-platform Flutter/Dart with single codebase",
        "platform": "cross-platform",
        "language": "dart",
        "keywords": ["flutter", "dart", "cross-platform"],
        "estimated_duration_multiplier": 1.0,
        "pros": ["Single codebase", "Fast iteration", "Good UI consistency"],
        "cons": ["Platform-specific plugins needed", "Larger binary size"],
        "risk_modifier": 0.0,
        "confidence_modifier": 0.0,
    },
    "native_android": {
        "label": "Native Android",
        "description": "Platform-native Kotlin/Jetpack Compose",
        "platform": "android",
        "language": "kotlin",
        "keywords": ["kotlin", "android", "jetpack", "compose", "material"],
        "estimated_duration_multiplier": 1.2,
        "pros": ["Full platform access", "Best performance", "Mature tooling"],
        "cons": ["Android-only", "Slower iteration than cross-platform"],
        "risk_modifier": -0.02,
        "confidence_modifier": 0.05,
    },
    "react_native": {
        "label": "React Native",
        "description": "JavaScript/TypeScript with React Native bridge",
        "platform": "cross-platform",
        "language": "typescript",
        "keywords": ["react native", "typescript", "javascript", "expo"],
        "estimated_duration_multiplier": 1.1,
        "pros": ["Large ecosystem", "Web skills transfer", "Fast prototyping"],
        "cons": ["Bridge performance overhead", "Native module complexity"],
        "risk_modifier": 0.05,
        "confidence_modifier": -0.03,
    },
    "web_first": {
        "label": "Web-First (PWA)",
        "description": "Responsive web app with progressive enhancement",
        "platform": "web",
        "language": "typescript",
        "keywords": ["web", "pwa", "responsive", "react", "nextjs"],
        "estimated_duration_multiplier": 0.8,
        "pros": ["No app store", "Instant updates", "Lowest cost"],
        "cons": ["Limited device access", "Offline complexity", "Less discoverable"],
        "risk_modifier": 0.03,
        "confidence_modifier": -0.02,
    },
    "ios_first": {
        "label": "iOS Native",
        "description": "Platform-native Swift/SwiftUI",
        "platform": "ios",
        "language": "swift",
        "keywords": ["swift", "swiftui", "ios", "apple", "xcode"],
        "estimated_duration_multiplier": 1.2,
        "pros": ["Best iOS experience", "Latest APIs first", "Higher revenue per user"],
        "cons": ["Apple ecosystem lock-in", "Stricter app review"],
        "risk_modifier": 0.02,
        "confidence_modifier": 0.0,
    },
    "backend_first": {
        "label": "Backend-First",
        "description": "API-first design, then thin client",
        "platform": "backend",
        "language": "python",
        "keywords": ["api", "backend", "server", "fastapi", "graphql"],
        "estimated_duration_multiplier": 0.9,
        "pros": ["Clear API contract", "Multiple client support", "Easier testing"],
        "cons": ["Client work still needed later", "Over-engineering risk"],
        "risk_modifier": -0.03,
        "confidence_modifier": 0.03,
    },
}

DEFAULT_STRATEGIES = ["flutter", "native_android", "react_native", "web_first"]


def infer_strategies(goal: str) -> list[str]:
    """Infer relevant strategies from the goal text."""
    gl = goal.lower()
    strategies = []

    # Platform hints
    if "ios" in gl or "apple" in gl or "swift" in gl:
        strategies.append("ios_first")
    if "android" in gl or "kotlin" in gl:
        strategies.append("native_android")
    if "web" in gl or "pwa" in gl or "browser" in gl:
        strategies.append("web_first")
    if "cross" in gl or "flutter" in gl:
        strategies.append("flutter")
    if "api" in gl or "backend" in gl or "server" in gl:
        strategies.append("backend_first")

    # Mobile app default set
    mobile_kw = {"mobile", "app", "phone", "tablet"}
    if mobile_kw & set(gl.split()):
        if "native_android" not in strategies:
            strategies.append("native_android")
        if "flutter" not in strategies:
            strategies.append("flutter")
        if "react_native" not in strategies:
            strategies.append("react_native")

    # Fallback
    if not strategies:
        strategies = list(DEFAULT_STRATEGIES)

    return strategies[:5]


# ── StrategyGenerator ────────────────────────────────────────────────────────


class StrategyGenerator:
    """Generates N candidate plan decompositions from a single goal.

    Each strategy produces a different plan tree by:
      - Injecting strategy-specific keywords into the decomposition
      - Adding strategy-specific setup tasks
      - Adjusting estimated durations
    """

    def __init__(self) -> None:
        self._decomposer = GoalDecomposer()

    def generate(
        self, goal: str, strategies: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate candidate plans for the given strategies.

        Returns a list of dicts with keys:
          strategy_key, strategy_label, plan (dict), root_node (dict),
          estimated_duration_days (float), estimated_cost (str).
        """
        if strategies is None:
            strategies = infer_strategies(goal)

        candidates: list[dict[str, Any]] = []
        seen_labels: set[str] = set()

        for strat_key in strategies:
            strat_def = STRATEGY_REGISTRY.get(strat_key)
            if not strat_def:
                continue
            label = strat_def["label"]
            if label in seen_labels:
                continue
            seen_labels.add(label)

            plan = self._generate_for_strategy(goal, strat_key, strat_def)
            candidates.append(plan)

        return candidates

    def _generate_for_strategy(
        self, goal: str, strat_key: str, strat_def: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a single candidate plan for one strategy."""
        # Inject strategy-related keywords into a copy of the goal
        # so the decomposer picks up relevant patterns.
        augmented_goal = goal
        keywords = strat_def.get("keywords", [])
        if keywords:
            # Add strategy keywords to goal if not already present
            missing = [kw for kw in keywords if kw not in goal.lower()]
            if missing:
                augmented_goal = f"{goal} using {', '.join(missing[:3])}"

        subgoal = self._decomposer.decompose(augmented_goal)

        # Estimate duration based on leaf count × strategy multiplier
        leaves = subgoal.flatten()
        multiplier = strat_def.get("estimated_duration_multiplier", 1.0)
        base_days = max(len(leaves) * 3, 5)
        est_days = round(base_days * multiplier)

        # Cost estimate (simple heuristic)
        platform = strat_def.get("platform", "")
        if platform in ("android", "ios"):
            est_cost = "medium"
        elif platform == "cross-platform":
            est_cost = "low"
        else:
            est_cost = "low"

        # Build the plan tree dict
        root_dict = _subgoal_to_dict(subgoal)
        root_dict["id"] = "root"

        return {
            "strategy_key": strat_key,
            "strategy_label": strat_def.get("label", strat_key),
            "strategy_description": strat_def.get("description", ""),
            "root_node": root_dict,
            "estimated_duration_days": est_days,
            "estimated_cost": est_cost,
            "pros": strat_def.get("pros", []),
            "cons": strat_def.get("cons", []),
            "risk_modifier": strat_def.get("risk_modifier", 0.0),
            "confidence_modifier": strat_def.get("confidence_modifier", 0.0),
        }


def _subgoal_to_dict(sg: SubGoal) -> dict[str, Any]:
    return {
        "id": sg.id,
        "title": sg.description[:80],
        "description": sg.description,
        "assigned_agent": sg.agent_id,
        "estimated_duration": None,
        "priority": 0,
        "status": sg.status,
        "children": [_subgoal_to_dict(c) for c in sg.children],
    }
