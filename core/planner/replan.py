"""ReplanEngine — generates alternative plans and computes improvement deltas.

Bridges PlanHealthEngine signals into the comparative planning system
to produce actionable replan options with expected improvement.
"""

from __future__ import annotations

import logging
from typing import Any

from core.planner.store import PlanStore
from core.planner.strategies import StrategyGenerator, infer_strategies
from core.planner.comparison import ComparativeScorer
from core.planner.health import PlanHealthEngine

logger = logging.getLogger(__name__)

_CURRENT_PLAN_KEYWORDS: dict[str, list[str]] = {
    "current": ["default", "baseline", "current", ""],
}


def _classify_plan_approach(plan: dict) -> str:
    """Guess which strategy category the current plan uses."""
    goal = plan.get("goal", "").lower()
    if "react" in goal or "js" in goal or "javascript" in goal or "web" in goal:
        return "react_native"
    if "flutter" in goal:
        return "flutter"
    if "native" in goal or "android" in goal:
        return "native_android"
    if "pwa" in goal or "progressive" in goal:
        return "web_pwa"
    if "ios" in goal or "swift" in goal:
        return "ios_native"
    if "backend" in goal or "api" in goal:
        return "backend_first"
    return "current"


class ReplanEngine:
    """Generates replan options with improvement deltas."""

    def __init__(self) -> None:
        self._plan_store = PlanStore()
        self._health_engine = PlanHealthEngine()
        self._strategy_generator = StrategyGenerator()
        self._scorer = ComparativeScorer()

    def get_options(self, plan_id: str) -> dict[str, Any]:
        """Return replan options for a given plan."""
        plan = self._plan_store.get(plan_id)
        if plan is None:
            return {"error": "Plan not found"}

        goal = plan["goal"]
        current_approach = _classify_plan_approach(plan)

        # Score current plan as a baseline
        base_score = self._score_current_plan(plan, current_approach)

        # Generate alternative strategies
        strategies = infer_strategies(goal)
        # Filter out the current approach to avoid duplicates
        alt_strategies = [s for s in strategies if s != current_approach]
        if not alt_strategies:
            alt_strategies = strategies  # fall back to all if only one

        candidates = self._strategy_generator.generate(goal, alt_strategies)

        # Score alternatives
        comparison = self._scorer.compare(goal, candidates)
        scored_candidates = comparison.get("candidates", [])

        # Compute deltas relative to current plan
        options = []
        for c in scored_candidates:
            delta = _compute_delta(base_score, c)
            options.append({
                "strategy": c.get("strategy_label", c.get("strategy_key", "unknown")),
                "strategy_key": c.get("strategy_key", ""),
                "description": c.get("strategy_description", c.get("description", "")),
                "pros": c.get("pros", []),
                "cons": c.get("cons", []),
                "score": round(c.get("overall_score", 0) * 100, 1),
                "delta": delta,
            })

        # Sort by delta.overall (descending — higher improvement first)
        options.sort(key=lambda o: o["delta"]["overall_change"], reverse=True)

        # Evaluate current health
        health = self._health_engine.evaluate(plan_id)

        return {
            "plan_id": plan_id,
            "goal": goal,
            "current_strategy": current_approach,
            "current_score": base_score.get("score", 0),
            "current_health": health.get("status", "unknown"),
            "health_score": health.get("health_score", 1.0),
            "options": options,
            "option_count": len(options),
            "evaluated_at": __import__("datetime").datetime.utcnow().isoformat(),
        }

    def _score_current_plan(self, plan: dict, approach: str) -> dict:
        """Score the current plan as if it were a comparison candidate."""
        leaves = _count_leaves(plan.get("root_node", {}))
        confidence = plan.get("metadata", {}).get("confidence_at_creation", 0.5)
        risks = len(plan.get("root_node", {}).get("risks", []))
        return {
            "strategy": approach,
            "score": round(confidence * 100, 1),
            "estimated_duration_days": 10,
            "risk_modifier": 0.0,
            "metrics": {
                "confidence": confidence,
                "leaves": leaves,
                "risks": risks,
            },
        }


def _count_leaves(node: dict) -> int:
    children = node.get("children", [])
    if not children:
        return 1
    return sum(_count_leaves(c) for c in children)


def _compute_delta(base: dict, candidate: dict) -> dict:
    """Compute the difference between current plan and a candidate."""
    base_score = base.get("score", 0)
    cand_score = candidate.get("overall_score", 0) * 100  # scorer returns 0-1

    overall_change = round((cand_score - base_score) / max(base_score, 1), 3)

    # Expected improvement categories
    improved_confidence = cand_score > base_score + 5
    cand_risk_mod = candidate.get("risk_modifier", 0)
    base_risk_mod = base.get("risk_modifier", 0)
    reduced_risk = cand_risk_mod < base_risk_mod
    cand_dur = candidate.get("estimated_duration_days", 14)
    base_dur = base.get("estimated_duration_days", 14)
    faster = cand_dur < base_dur

    expected_improvements = []
    if overall_change > 0:
        expected_improvements.append("+confidence")
    if reduced_risk:
        expected_improvements.append("-risk")
    if faster:
        expected_improvements.append("-duration")

    return {
        "overall_change": overall_change,
        "score_change": round(cand_score - base_score, 1),
        "confidence_change": round(
            candidate.get("dimensions", {}).get("confidence", 0.5)
            - base.get("metrics", {}).get("confidence", 0.5),
            2,
        ),
        "expected_improvements": expected_improvements or ["neutral"],
    }


# ── Direct replan action ─────────────────────────────────────────────────────


def execute_replan(plan_id: str, strategy: str | None = None) -> dict[str, Any] | None:
    """Replan using a specific strategy; returns updated plan or None."""
    plan_store = PlanStore()
    plan = plan_store.get(plan_id)
    if plan is None:
        return None

    goal = plan["goal"]

    if strategy and strategy != "current":
        generator = StrategyGenerator()
        candidates = generator.generate(goal, [strategy])
        if candidates:
            candidate = candidates[0]
            from core.planner.store import _subgoal_to_dict
            new_root = candidate.get("root_node") or _subgoal_to_dict(
                candidate.get("subgoal", candidate)
            )
        else:
            new_root = None
    else:
        # Standard replan (no specific strategy) — re-decompose
        from core.planner.decomposer import GoalDecomposer
        from core.planner.store import _subgoal_to_dict
        decomposer = GoalDecomposer()
        subgoal = decomposer.decompose(goal)
        new_root = _subgoal_to_dict(subgoal)

    if new_root:
        import uuid
        now = __import__("datetime").datetime.utcnow().isoformat()
        plan_store.update_status(plan_id, "draft")
        plan_store.update_node(plan_id, "root", {
            "children": new_root.get("children", []),
            "last_replanned": now,
        })
        if strategy:
            plan_store.update_node(plan_id, "root", {"strategy": strategy})

        plan = plan_store.get(plan_id)
        logger.info("Replan: executed replan for %s with strategy=%s", plan_id, strategy or "default")
        return plan

    return None
