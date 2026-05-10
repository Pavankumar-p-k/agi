# api/agi_routes.py
#
# AGI REST API — all AGI capabilities exposed as endpoints
#
# Add to your existing main.py:
#   from api.agi_routes import router as agi_router
#   app.include_router(agi_router)
#   # startup: await get_agi().start()

import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from core.agi_core import get_agi


router = APIRouter(prefix="/agi", tags=["agi"])


# ── Request models ─────────────────────────────────────────

class GoalRequest(BaseModel):
    description: str
    context:     dict = {}

class SolveRequest(BaseModel):
    problem:  str
    context:  dict = {}

class HabitRequest(BaseModel):
    description:  str
    trigger_hour: int
    trigger_days: list = list(range(7))
    action:       str = "speak"
    params:       dict = {}

class ConfigRequest(BaseModel):
    autonomous_enabled:   Optional[bool]  = None
    confidence_threshold: Optional[float] = None
    dnd_mode:             Optional[bool]  = None
    dnd_hours:            Optional[list]  = None


# ── Routes ─────────────────────────────────────────────────

@router.get("/status")
async def agi_status():
    """Current AGI status, loop count, goals, decisions."""
    agi = get_agi()
    stats = await agi.memory.get_stats()
    return {
        **agi.get_status(),
        "memory_stats":     stats,
        "reflector_stats":  agi.reflector.get_stats(),
        "last_predictions": agi.predictor.get_last_predictions(),
    }


@router.post("/goal")
async def create_goal(req: GoalRequest):
    """
    Give JARVIS a goal to pursue autonomously.
    JARVIS will break it into steps and execute them.

    Examples:
    - "Send Rahul a follow-up message every morning this week"
    - "Organize all my notes from this week"
    - "Set study reminders for my exam on Monday"
    """
    agi    = get_agi()
    goal_id = await agi.set_goal(req.description, req.context)
    return {"goal_id": goal_id, "status": "created"}


@router.get("/goals")
async def list_goals():
    """List all active and completed goals."""
    agi = get_agi()
    return {"goals": agi.get_goals()}


@router.post("/solve")
async def solve_problem(req: SolveRequest):
    """
    Solve a complex problem step by step.
    Returns the plan and execution results.

    Examples:
    - "I need to prepare for my exam on Monday"
    - "Organize all my tasks for this week"
    - "Help me plan a surprise for a friend's birthday"
    """
    agi    = get_agi()
    result = await agi.solve(req.problem, req.context)
    return {
        "problem":      result.problem,
        "steps_total":  result.steps_total,
        "steps_done":   result.steps_done,
        "steps_failed": result.steps_failed,
        "success":      result.success,
        "output":       result.output,
        "duration_s":   result.duration_s,
    }


@router.get("/patterns")
async def get_patterns():
    """View all learned behavioral patterns."""
    agi = get_agi()
    return {
        "patterns":    agi.patterns.get_all_patterns(),
        "habits":      agi.habits.get_habits(),
        "habit_summary": agi.habits.get_daily_summary(),
    }


@router.get("/predictions")
async def get_predictions():
    """See what JARVIS is currently predicting you'll need."""
    agi   = get_agi()
    state = await agi._observe()
    predictions = await agi.predictor.predict(state)
    return {
        "state":       {"hour": state.hour, "mood": state.pavan_mood, "weekend": state.is_weekend},
        "predictions": predictions,
    }


@router.post("/habit")
async def add_habit(req: HabitRequest):
    """Add a recurring habit for JARVIS to act on automatically."""
    agi = get_agi()
    h_id = agi.habits.add_habit(
        description=req.description,
        trigger_hour=req.trigger_hour,
        trigger_days=req.trigger_days,
        action=req.action,
        params=req.params,
    )
    return {"habit_id": h_id, "status": "added"}


@router.get("/decisions")
async def get_decisions(n: int = 20):
    """View JARVIS's recent autonomous decisions."""
    agi = get_agi()
    return {
        "decisions": agi.get_decision_history(n),
        "total":     len(agi._decision_history),
    }


@router.get("/reflections")
async def get_reflections():
    """View JARVIS's self-improvement reflections."""
    agi = get_agi()
    return agi.reflector.get_stats()


@router.post("/config")
async def configure_agi(req: ConfigRequest):
    """Configure AGI behavior."""
    agi = get_agi()
    changes = {}

    if req.autonomous_enabled is not None:
        agi.toggle_autonomous(req.autonomous_enabled)
        changes["autonomous"] = req.autonomous_enabled

    if req.confidence_threshold is not None:
        agi.set_confidence_threshold(req.confidence_threshold)
        changes["confidence_threshold"] = req.confidence_threshold

    if req.dnd_mode is not None:
        agi.goal_planner.set_dnd(req.dnd_mode, req.dnd_hours or [])
        changes["dnd_mode"] = req.dnd_mode

    return {"updated": changes}


@router.post("/trigger")
async def manual_trigger():
    """Manually trigger one AGI loop cycle (for testing)."""
    agi = get_agi()
    state = await agi._observe()
    await agi.patterns.learn_from_state(state)
    predictions = await agi.predictor.predict(state)
    return {
        "state":       {"hour": state.hour, "mood": state.pavan_mood},
        "predictions": predictions,
        "loop_count":  agi._loop_count,
    }


# ── INTEGRATION: add these to your existing main.py ──────────
#
#  from api.agi_routes import router as agi_router
#  from core.agi_core import get_agi
#
#  app.include_router(agi_router)
#
#  @app.on_event("startup")
#  async def on_startup():
#      brain = get_brain()
#      await brain.startup()
#      agi = get_agi()
#      await agi.start()         # ← starts AGI background loop
#
#  # Hook AGI into every chat:
#  @app.post("/api/chat")
#  async def chat(body: dict):
#      result = await get_brain().think(Message(text=body["message"]))
#      # Tell AGI about this interaction
#      asyncio.create_task(
#          get_agi().on_user_input(
#              body["message"], result.intent, result.emotion
#          )
#      )
#      return {"response": result.reply}
