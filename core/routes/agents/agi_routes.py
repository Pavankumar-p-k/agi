from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from fastapi import Response


@dataclass
class HabitRequest:
    description: str
    trigger_hour: int


@dataclass
class ConfigRequest:
    dnd_mode: bool
    dnd_hours: list[int]


_agi_instance: Any = None


def get_agi() -> Any:
    return _agi_instance


async def agi_status() -> dict:
    agi = get_agi()
    memory_stats = {}
    if agi.memory is not None:
        memory_stats = await agi.memory.get_stats()
    else:
        memory_stats = {"info": "not connected"}
    reflector_stats = {}
    if agi.reflector is not None:
        reflector_stats = agi.reflector.get_stats()
    last_predictions = []
    if agi.predictor is not None:
        last_predictions = agi.predictor.get_last_predictions()
    return {
        "memory_stats": memory_stats,
        "reflector_stats": reflector_stats,
        "last_predictions": last_predictions,
    }


async def get_patterns() -> dict:
    agi = get_agi()
    patterns = []
    if agi.patterns is not None:
        patterns = agi.patterns.get_all_patterns()
    habits = []
    habit_summary = None
    if agi.habits is not None:
        habits = agi.habits.get_habits()
        habit_summary = agi.habits.get_daily_summary()
    result = {"patterns": patterns, "habits": habits}
    if habit_summary is not None:
        result["habit_summary"] = habit_summary
    return result


async def get_predictions() -> dict:
    agi = get_agi()
    obs = await agi._observe()
    predictions = []
    if agi.predictor is not None:
        predictions = await agi.predictor.predict(obs)
    return {"predictions": predictions}


async def add_habit(req: HabitRequest) -> dict | Response:
    agi = get_agi()
    if agi.habits is None:
        return Response(status_code=501)
    habit_id = agi.habits.add_habit(req.description, req.trigger_hour)
    return {"habit_id": habit_id, "status": "added"}


async def get_reflections() -> dict | Response:
    agi = get_agi()
    if agi.reflector is None:
        return Response(status_code=501)
    return agi.reflector.get_stats()


async def manual_trigger() -> dict:
    agi = get_agi()
    obs = await agi._observe()
    if agi.patterns is not None:
        await agi.patterns.learn_from_state(obs)
    predictions = []
    if agi.predictor is not None:
        predictions = await agi.predictor.predict(obs)
    return {"predictions": predictions, "loop_count": agi._loop_count}


async def configure_agi(req: ConfigRequest) -> dict | Response:
    agi = get_agi()
    if agi.goal_planner is None:
        return Response(status_code=501)
    agi.goal_planner.dnd_mode = req.dnd_mode
    agi.goal_planner.dnd_hours = req.dnd_hours
    return {"updated": {"dnd_mode": req.dnd_mode}}
