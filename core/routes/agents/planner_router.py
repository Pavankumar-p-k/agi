"""core/routes/planner.py — REST API for Plans.

First-class plan resources with full lifecycle:
  draft → approve → execute → replan → complete/fail

Also supports node-level editing (rename, reorder, reassign) so the
Planner Studio UI can intervene at the plan level before scheduling.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.planner.store import PlanStore
from core.planner.strategies import StrategyGenerator, infer_strategies
from core.planner.comparison import ComparativeScorer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plans", tags=["Planner"])

# ── Singleton store ─────────────────────────────────────────────────────────

_store: PlanStore | None = None


def _get_store() -> PlanStore:
    global _store
    if _store is None:
        _store = PlanStore()
    return _store


# ── Pydantic models ─────────────────────────────────────────────────────────


class CreatePlanRequest(BaseModel):
    goal: str


class UpdateNodeRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    assigned_agent: str | None = None
    estimated_duration: int | None = None
    priority: int | None = None
    status: str | None = None


class ReplanRequest(BaseModel):
    modified_goal: str | None = None


class CompareRequest(BaseModel):
    goal: str
    strategies: list[str] | None = None


class ReplanOptionsRequest(BaseModel):
    strategy: str | None = None


class PlanNodeResponse(BaseModel):
    id: str
    title: str
    description: str
    assigned_agent: str | None = None
    estimated_duration: int | None = None
    priority: int = 0
    status: str = "pending"
    children: list[PlanNodeResponse] = []


class PlanResponse(BaseModel):
    id: str
    goal: str
    status: str
    root_node: PlanNodeResponse
    created_at: str
    updated_at: str


class PlanListResponse(BaseModel):
    plans: list[PlanResponse]
    total: int


def _dict_to_node(d: dict[str, Any]) -> PlanNodeResponse:
    return PlanNodeResponse(
        id=d.get("id", ""),
        title=d.get("title", ""),
        description=d.get("description", ""),
        assigned_agent=d.get("assigned_agent"),
        estimated_duration=d.get("estimated_duration"),
        priority=d.get("priority", 0),
        status=d.get("status", "pending"),
        children=[_dict_to_node(c) for c in d.get("children", [])],
    )


def _plan_to_response(p: dict[str, Any]) -> PlanResponse:
    return PlanResponse(
        id=p["id"],
        goal=p["goal"],
        status=p["status"],
        root_node=_dict_to_node(p.get("root_node", {})),
        created_at=p["created_at"],
        updated_at=p["updated_at"],
    )


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("")
def list_plans(
    status: str | None = Query(None, description="Filter by status"),
) -> PlanListResponse:
    plans = _get_store().list_all(status=status)
    return PlanListResponse(
        plans=[_plan_to_response(p) for p in plans],
        total=len(plans),
    )


@router.get("/{plan_id}")
def get_plan(plan_id: str) -> PlanResponse:
    plan = _get_store().get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return _plan_to_response(plan)


@router.post("", status_code=201)
def create_plan(req: CreatePlanRequest) -> PlanResponse:
    store = _get_store()
    plan = store.create(goal=req.goal)
    logger.info("Planner: created plan %s for goal=%r", plan["id"], req.goal[:60])
    return _plan_to_response(plan)


@router.post("/{plan_id}/approve")
def approve_plan(plan_id: str) -> PlanResponse:
    store = _get_store()
    plan = store.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan["status"] not in ("draft", "rejected"):
        raise HTTPException(status_code=409, detail=f"Cannot approve plan in status {plan['status']}")
    store.update_status(plan_id, "approved")
    plan["status"] = "approved"
    logger.info("Planner: approved plan %s", plan_id)
    return _plan_to_response(plan)


@router.post("/{plan_id}/reject")
def reject_plan(plan_id: str) -> PlanResponse:
    store = _get_store()
    plan = store.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    store.update_status(plan_id, "rejected")
    plan["status"] = "rejected"
    logger.info("Planner: rejected plan %s", plan_id)
    return _plan_to_response(plan)


@router.post("/{plan_id}/execute")
def execute_plan(plan_id: str) -> PlanResponse:
    store = _get_store()
    plan = store.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan["status"] != "approved":
        raise HTTPException(status_code=409, detail=f"Cannot execute plan in status {plan['status']}")
    store.update_status(plan_id, "executing")
    plan["status"] = "executing"

    # Flatten leaf nodes and create scheduled activities
    _schedule_plan_nodes(plan)

    # Record predicted metrics as outcome baseline
    try:
        from core.planner.outcomes import PlanOutcomeStore
        outcome_store = PlanOutcomeStore()
        leaves = _flatten_plan_nodes(plan.get("root_node", {}))
        predicted = _compute_predicted_metrics(plan, leaves)
        outcome_store.create(plan_id=plan_id, **predicted)
        logger.info("Planner: created outcome record for plan %s", plan_id)
    except Exception as e:
        logger.warning("Planner: failed to record outcome for %s: %s", plan_id, e)

    logger.info("Planner: executing plan %s", plan_id)
    return _plan_to_response(plan)


@router.post("/{plan_id}/replan")
def replan_plan(plan_id: str) -> PlanResponse:
    store = _get_store()
    plan = store.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Regenerate decomposition from the original goal
    try:
        from core.planner.decomposer import GoalDecomposer
        from core.planner.store import _subgoal_to_dict
        decomposer = GoalDecomposer()
        subgoal = decomposer.decompose(plan["goal"])
        new_root = _subgoal_to_dict(subgoal)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Replanning failed: {e}")

    now = datetime.utcnow().isoformat()
    store.update_status(plan_id, "draft")
    store.update_node(plan_id, "root", {"children": new_root.get("children", [])})
    plan = store.get(plan_id)
    logger.info("Planner: replanned %s", plan_id)
    return _plan_to_response(plan)


@router.patch("/{plan_id}/nodes/{node_id}")
def update_plan_node(plan_id: str, node_id: str, req: UpdateNodeRequest) -> PlanResponse:
    store = _get_store()
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    updated = store.update_node(plan_id, node_id, patch)
    if updated is None:
        raise HTTPException(status_code=404, detail="Plan or node not found")
    logger.info("Planner: updated node %s in plan %s", node_id, plan_id)
    return _plan_to_response(updated)


@router.delete("/{plan_id}")
def delete_plan(plan_id: str) -> dict:
    store = _get_store()
    plan = store.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    store.delete(plan_id)
    logger.info("Planner: deleted plan %s", plan_id)
    return {"deleted": plan_id}


# ── Compare route ────────────────────────────────────────────────────────────


@router.post("/compare")
def compare_plans(req: CompareRequest) -> dict:
    """Generate and compare multiple candidate plans for a goal."""
    strategies = req.strategies or infer_strategies(req.goal)
    generator = StrategyGenerator()
    candidates = generator.generate(req.goal, strategies)

    if not candidates:
        raise HTTPException(status_code=400, detail="No strategies could be generated")

    scorer = ComparativeScorer()
    comparison = scorer.compare(req.goal, candidates)
    logger.info("Planner: compared %d strategies for goal=%r", len(candidates), req.goal[:60])
    return comparison


# ── Evidence routes ─────────────────────────────────────────────────────────


@router.get("/{plan_id}/evidence")
def get_plan_evidence(plan_id: str) -> dict:
    from core.planner.evidence import PlanEvidenceEngine
    eng = PlanEvidenceEngine()
    result = eng.get_evidence(plan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return result


@router.get("/{plan_id}/risks")
def get_plan_risks(plan_id: str) -> dict:
    from core.planner.evidence import PlanEvidenceEngine
    eng = PlanEvidenceEngine()
    result = eng.get_risks(plan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return result


@router.get("/{plan_id}/alternatives")
def get_plan_alternatives(plan_id: str) -> dict:
    from core.planner.evidence import PlanEvidenceEngine
    eng = PlanEvidenceEngine()
    result = eng.get_alternatives(plan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return result


@router.get("/{plan_id}/confidence")
def get_plan_confidence(plan_id: str) -> dict:
    from core.planner.evidence import PlanEvidenceEngine
    eng = PlanEvidenceEngine()
    result = eng.get_confidence(plan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return result


# ── Outcome routes ──────────────────────────────────────────────────────────


@router.get("/{plan_id}/outcome")
def get_plan_outcome(plan_id: str) -> dict:
    from core.planner.outcomes import compute_plan_outcome
    result = compute_plan_outcome(plan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No outcome data for this plan")
    return result


@router.get("/{plan_id}/prediction")
def get_plan_prediction(plan_id: str) -> dict:
    from core.planner.outcomes import PlanOutcomeStore
    store = PlanOutcomeStore()
    outcome = store.get(plan_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="No prediction data for this plan")
    return {
        "plan_id": plan_id,
        "predicted_confidence": outcome["predicted_confidence"],
        "predicted_success_rate": outcome["predicted_success_rate"],
        "predicted_duration_days": outcome["predicted_duration_days"],
        "predicted_risk_score": outcome["predicted_risk_score"],
        "predicted_cost": outcome["predicted_cost"],
        "executed_at": outcome.get("executed_at"),
        "completed_at": outcome.get("completed_at"),
    }


@router.get("/{plan_id}/accuracy")
def get_plan_accuracy(plan_id: str) -> dict:
    from core.planner.outcomes import get_prediction_accuracy
    result = get_prediction_accuracy(plan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Cannot compute accuracy for this plan")
    return result


# ── Health & Replan routes ──────────────────────────────────────────────────


@router.get("/{plan_id}/health")
def get_plan_health(plan_id: str) -> dict:
    from core.planner.health import PlanHealthEngine
    eng = PlanHealthEngine()
    return eng.evaluate(plan_id)


@router.get("/{plan_id}/replan-options")
def get_replan_options(plan_id: str) -> dict:
    from core.planner.replan import ReplanEngine
    eng = ReplanEngine()
    options = eng.get_options(plan_id)
    if "error" in options:
        raise HTTPException(status_code=404, detail=options["error"])
    return options


@router.post("/{plan_id}/replan")
def replan_plan_v2(plan_id: str, req: ReplanOptionsRequest) -> PlanResponse:
    """Replan using an optional specific strategy. Replaces the old replan endpoint for strategy-aware replanning."""
    from core.planner.replan import execute_replan
    plan = execute_replan(plan_id, strategy=req.strategy)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return _plan_to_response(plan)


@router.post("/{plan_id}/auto-replan")
def auto_replan(plan_id: str) -> dict:
    """Evaluate plan health and, if warranted, auto-replan with the best available strategy."""
    from core.planner.health import PlanHealthEngine
    from core.planner.replan import ReplanEngine, execute_replan

    health_eng = PlanHealthEngine()
    health = health_eng.evaluate(plan_id)
    status = health.get("status", "unknown")

    if status in ("replan_required", "replan_recommended"):
        replan_eng = ReplanEngine()
        options_result = replan_eng.get_options(plan_id)
        options = options_result.get("options", [])
        if options:
            best = options[0]  # highest delta.overall_change
            strategy = best["strategy"]
            plan = execute_replan(plan_id, strategy=strategy)
            if plan:
                return {
                    "status": status,
                    "action": "replanned",
                    "strategy": strategy,
                    "expected_improvement": best.get("delta", {}),
                    "plan": _plan_to_response(plan),
                    "health_before": health,
                }
        # Fall back to standard replan
        plan = execute_replan(plan_id)
        if plan:
            return {
                "status": status,
                "action": "replanned_default",
                "plan": _plan_to_response(plan),
                "health_before": health,
            }

    return {
        "status": status,
        "action": "no_action_needed",
        "health": health,
        "message": "Plan health is adequate — no replan required.",
    }


# ── Helpers for outcome recording ───────────────────────────────────────────


def _flatten_plan_nodes(node: dict) -> list[dict]:
    nodes = []
    queue = [node]
    while queue:
        cur = queue.pop(0)
        nodes.append(cur)
        queue.extend(cur.get("children", []))
    return nodes


def _compute_predicted_metrics(plan: dict, leaves: list[dict]) -> dict:
    # Average priority as confidence proxy
    priorities = [n.get("priority", 0) for n in leaves]
    avg_priority = sum(priorities) / max(len(priorities), 1)
    confidence = min(0.95, 0.5 + avg_priority * 0.1)

    # Duration: 3 days per leaf, plus some overhead
    dur = max(2, len(leaves) * 3)

    # Risk: higher with more leaves
    risk = min(0.9, 0.1 + len(leaves) * 0.05)

    return {
        "predicted_confidence": round(confidence, 2),
        "predicted_success_rate": round(confidence * 0.9, 2),
        "predicted_duration_days": dur,
        "predicted_risk_score": round(risk, 2),
        "predicted_cost": "low" if dur <= 5 else "medium" if dur <= 15 else "high",
    }


# ── Scheduling helper ───────────────────────────────────────────────────────


def _schedule_plan_nodes(plan: dict[str, Any]) -> None:
    """Flatten leaf nodes and register them as scheduled activities.

    Each leaf becomes a pending activity in the scheduler queue with
    its assigned agent, priority, and goal mapped from plan node fields.
    The plan ID is stored in metadata for back-linking.
    """
    leaves: list[dict[str, Any]] = []

    def _collect_leaves(node: dict[str, Any]) -> None:
        children = node.get("children", [])
        if not children:
            leaves.append(node)
        else:
            for c in children:
                _collect_leaves(c)

    _collect_leaves(plan.get("root_node", {}))

    try:
        from core.scheduler.models import ScheduledActivity
        from core.scheduler.store import SchedulerStore

        sched_store = SchedulerStore()
        for leaf in leaves:
            act = ScheduledActivity(
                activity_id=f"act_{uuid.uuid4().hex[:12]}",
                priority=leaf.get("priority", 0),
                score=50,
                status="pending",
                goal=leaf.get("description", leaf.get("title", "")),
                node_type="plan_task",
                depends_on=[],
                metadata={
                    "plan_id": plan["id"],
                    "plan_node_id": leaf.get("id", ""),
                    "assigned_agent": leaf.get("assigned_agent"),
                },
            )
            sched_store.add(act)
            logger.debug("Planner: scheduled activity %s from plan %s", act.activity_id, plan["id"])
    except Exception as e:
        logger.error("Planner: failed to schedule plan nodes: %s", e)
