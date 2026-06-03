"""core/plan_manager.py — PlanManager for Agent Orchestrator"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "plans"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class GoalProcessor:
    """Handles goal analysis and setup questions."""

    def build_setup_questions(self, goal: str) -> list[str]:
        return [
            f"Any specific preferences for '{goal[:40]}...?",
            "Estimated priority (low/medium/high)?",
        ]


class PlanManager:
    """Manages goal plans — create, approve, reject, execute, track status."""

    def __init__(self):
        self._plans: dict[str, dict] = {}
        self._goal_processor = GoalProcessor()
        self._executor = None
        self._load()

    def _load(self):
        for f in DATA_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                self._plans[data["id"]] = data
            except Exception as e:
                logger.warning("[PlanManager] Failed to load %s: %s", f.name, e)

    def _save(self, plan: dict):
        path = DATA_DIR / f"{plan['id']}.json"
        path.write_text(json.dumps(plan, indent=2, default=str))

    async def create_plan(self, goal: str, preferences: dict | None = None) -> dict:
        plan = {
            "id": str(uuid.uuid4())[:8],
            "goal": goal,
            "preferences": preferences or {},
            "steps": [],
            "status": "pending_setup",
            "created_at": time.time(),
        }
        self._plans[plan["id"]] = plan
        self._save(plan)
        return plan

    def get_plan(self, plan_id: str) -> dict | None:
        return self._plans.get(plan_id)

    async def approve_plan(self, plan_id: str) -> dict | None:
        plan = self._plans.get(plan_id)
        if plan:
            plan["status"] = "approved"
            self._save(plan)
        return plan

    async def reject_plan(self, plan_id: str) -> dict | None:
        plan = self._plans.get(plan_id)
        if plan:
            plan["status"] = "rejected"
            self._save(plan)
        return plan

    async def execute_plan(self, plan_id: str):
        plan = self._plans.get(plan_id)
        if plan:
            plan["status"] = "executing"
            self._save(plan)
            await self._run_steps(plan)

    async def _run_steps(self, plan: dict):
        for step in plan.get("steps", []):
            logger.info("[PlanManager] Executing step: %s", step)
            await asyncio.sleep(0.1)
        plan["status"] = "completed"
        self._save(plan)

    async def get_status(self, plan_id: str) -> dict | None:
        plan = self._plans.get(plan_id)
        if not plan:
            return None
        return {"plan_id": plan["id"], "status": plan.get("status", "unknown")}

    async def list_plans(self) -> list[dict]:
        return [{"id": p["id"], "goal": p["goal"], "status": p["status"]} for p in self._plans.values()]
