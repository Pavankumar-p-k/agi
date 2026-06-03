"""core/agi_core.py — AGI Core that powers the /agi/* REST endpoints.
Wraps the sub-agent registry and provides the interface api/agi_routes.py expects.
"""
from __future__ import annotations
import asyncio
import time
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional, Any

from core.sub_agents.registry import agent_registry
from core.settings.store import get_settings_store

logger = logging.getLogger("jarvis.agi")


@dataclass
class SolveResult:
    problem: str = ""
    steps_total: int = 0
    steps_done: int = 0
    steps_failed: int = 0
    success: bool = False
    output: str = ""
    duration_s: float = 0.0


@dataclass
class _ObserveState:
    hour: int = 0
    pavan_mood: str = "neutral"
    is_weekend: bool = False


class _StubAttr:
    """
    Stub that raises NotImplementedError on access.
    Every attribute access here means a real module is not wired up yet.
    """
    def __init__(self, name: str = "unknown"):
        self._name = name

    def __getattr__(self, name: str):
        raise NotImplementedError(f"[STUB] {self._name}.{name} is not implemented yet.")


class AGICore:
    """Central AGI controller. Wires sub-agents into a unified interface."""

    def __init__(self):
        self._loop_count = 0
        self._decision_history: list[dict] = []
        self._goals: list[dict] = []
        self._settings = get_settings_store()
        self._started = False

        # Stubs for unimplemented modules — wire these to real classes in future
        try:
            self.memory = _StubAttr("memory_engine")
        except Exception:
            self.memory = None

        try:
            self.reflector = _StubAttr("reflector")
        except Exception:
            self.reflector = None

        try:
            self.predictor = _StubAttr("predictor")
        except Exception:
            self.predictor = None

        try:
            self.patterns = _StubAttr("pattern_engine")
        except Exception:
            self.patterns = None

        try:
            self.habits = _StubAttr("habit_engine")
        except Exception:
            self.habits = None

        try:
            self.goal_planner = _StubAttr("goal_planner")
        except Exception:
            self.goal_planner = None

        # Real sub-agent registry
        self.agent_pool = agent_registry

    # ── Lifecycle ───────────────────────────────────────────

    async def start(self):
        """Start AGI background loop (stub for now)."""
        if self._started:
            return
        self._started = True
        logger.info("[AGI] Started")
        # Background loop would go here

    async def stop(self):
        self._started = False
        logger.info("[AGI] Stopped")

    # ── Status ──────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "autonomous": self._settings.get("agi.autonomous_enabled"),
            "loop_count": self._loop_count,
            "confidence_threshold": self._settings.get("agi.confidence_threshold"),
            "goal_count": len(self._goals),
            "agents": [a["name"] for a in agent_registry.list_agents()],
        }

    def toggle_autonomous(self, enabled: bool):
        self._settings.set("agi.autonomous_enabled", enabled)

    def set_confidence_threshold(self, threshold: float):
        self._settings.set("agi.confidence_threshold", threshold)

    # ── Goals ───────────────────────────────────────────────

    async def set_goal(self, description: str, context: dict | None = None) -> str:
        goal_id = str(uuid.uuid4())[:8]
        self._goals.append({
            "id": goal_id,
            "description": description,
            "status": "running",
            "created_at": time.time(),
        })
        from core.sub_agents.registry import agent_registry
        try:
            asyncio.create_task(self._run_goal(goal_id, description, context or {}))
        except RuntimeError:
            # Fallback for sync context if needed
            logger.warning("[AGI] Cannot run goal background task - no event loop")
        return goal_id

    async def _run_goal(self, goal_id: str, description: str, context: dict):
        try:
            result = await agent_registry.run("ORACLE", description, mode="plan")
            output = result.output
            for goal in self._goals:
                if goal["id"] == goal_id:
                    goal["status"] = "done"
                    goal["output"] = output
        except Exception as e:
            logger.error(f"[AGI] Goal {goal_id} failed: {e}")
            for goal in self._goals:
                if goal["id"] == goal_id:
                    goal["status"] = "failed"
                    goal["error"] = str(e)

    def get_goals(self) -> list[dict]:
        return self._goals

    # ── Solve ───────────────────────────────────────────────

    async def solve(self, problem: str, context: dict | None = None) -> SolveResult:
        start = time.time()
        ctx = context or {}
        result = SolveResult(problem=problem)

        try:
            plan_result = await agent_registry.run("ORACLE", problem, mode="plan")
            result.steps_total = 1
            result.steps_done = 1
            result.output = plan_result.output
            result.success = plan_result.success
        except Exception as e:
            result.success = False
            result.output = f"Error: {e}"
            result.steps_failed = 1

        result.duration_s = time.time() - start
        return result

    # ── Observation ─────────────────────────────────────────

    async def _observe(self) -> _ObserveState:
        import datetime
        now = datetime.datetime.now()
        return _ObserveState(
            hour=now.hour,
            pavan_mood="neutral",
            is_weekend=now.weekday() >= 5,
        )

    # ── Decision History ────────────────────────────────────

    def get_decision_history(self, n: int = 20) -> list[dict]:
        return self._decision_history[-n:]

    def record_decision(self, decision: dict):
        self._decision_history.append(decision)

    # ── User Input Hook ─────────────────────────────────────

    async def on_user_input(self, message: str, intent: str, emotion: str):
        self._loop_count += 1
        self.record_decision({
            "input": message[:100],
            "intent": intent,
            "emotion": emotion,
            "timestamp": time.time(),
        })
        # Plugin hook: on_decision
        try:
            from core.plugins.registry import get_plugin_registry
            registry = get_plugin_registry()
            asyncio.create_task(registry.run_hook("on_decision", decision=self._decision_history[-1]))
        except Exception:
            pass


# ── Singleton ───────────────────────────────────────────────

_instance: AGICore | None = None


def get_agi() -> AGICore:
    global _instance
    if _instance is None:
        _instance = AGICore()
    return _instance
