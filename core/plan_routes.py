# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""core/plan_routes.py
FastAPI routes for JARVIS Agent Orchestrator — goal submission, plan management,
approval, and execution tracking.
"""

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("plan_routes")

_DATA_DIR = Path(__file__).parent.parent / "data" / "plans"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/api/plans", tags=["Agent Orchestrator"])


class _GoalProcessor:
    def build_setup_questions(self, goal: str) -> list[str]:
        return [
            f"Any specific preferences for '{goal[:40]}...?",
            "Estimated priority (low/medium/high)?",
        ]


class _PlanStore:
    def __init__(self):
        self._plans: dict[str, dict] = {}
        self._goal_processor = _GoalProcessor()
        self._executor = None
        self._load()

    def _load(self):
        for f in _DATA_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                self._plans[data["id"]] = data
            except Exception as e:
                logger.warning("[_PlanStore] Failed to load %s: %s", f.name, e)

    def _save(self, plan: dict):
        path = _DATA_DIR / f"{plan['id']}.json"
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
            logger.info("[_PlanStore] Executing step: %s", step)
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


plan_manager = _PlanStore()


class GoalRequest(BaseModel):
    goal: str
    preferences: dict | None = None


class ApprovalRequest(BaseModel):
    plan_id: str
    approve: bool
    modifications: dict | None = None


class SetupRequest(BaseModel):
    plan_id: str
    preferences: dict


@router.post("/goal")
async def submit_goal(req: GoalRequest):
    plan = await plan_manager.create_plan(req.goal, req.preferences)
    return {
        "plan_id": plan["id"],
        "goal": plan["goal"],
        "steps": plan.get("steps", []),
        "status": plan["status"],
        "setup_questions": plan_manager._goal_processor.build_setup_questions(req.goal),
    }


@router.post("/setup")
async def set_preferences(req: SetupRequest):
    plan = plan_manager.get_plan(req.plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    plan.update(req.preferences)
    plan["status"] = "pending_approval"
    return {"plan_id": req.plan_id, "status": "pending_approval"}


@router.post("/approve")
async def approve_plan(req: ApprovalRequest):
    if req.approve:
        plan = plan_manager.approve_plan(req.plan_id)
    else:
        plan = plan_manager.reject_plan(req.plan_id)

    if not plan:
        raise HTTPException(404, "Plan not found")

    return {"plan_id": req.plan_id, "status": plan["status"]}


@router.post("/{plan_id}/execute")
async def execute_plan(plan_id: str):
    plan = plan_manager.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    if plan["status"] != "approved":
        raise HTTPException(400, f"Plan must be approved first (current: {plan['status']})")

    asyncio.create_task(plan_manager.execute_plan(plan_id))
    return {"plan_id": plan_id, "status": "executing", "message": "Execution started"}


@router.get("/{plan_id}")
async def get_plan(plan_id: str):
    status = plan_manager.get_status(plan_id)
    if not status:
        raise HTTPException(404, "Plan not found")
    return status


@router.get("/{plan_id}/status")
async def get_plan_status(plan_id: str):
    status = plan_manager.get_status(plan_id)
    if not status:
        raise HTTPException(404, "Plan not found")
    return {"plan_id": plan_id, "status": status["status"], "details": status}


@router.post("/{plan_id}/cancel")
async def cancel_execution(plan_id: str):
    plan = plan_manager.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    if plan_manager._executor:
        plan_manager._executor.cancel()
    plan["status"] = "cancelled"
    return {"plan_id": plan_id, "status": "cancelled"}


@router.get("/")
async def list_plans():
    return {"plans": plan_manager.list_plans()}
