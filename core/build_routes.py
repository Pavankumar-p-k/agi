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
"""core/build_routes.py
FastAPI routes for the JARVIS autonomous build system.
Uses BuildService (ExecutionManager + WorkflowEngine) instead of legacy control_loop.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.build.service import build_service
from core.checkpoint_manager import checkpoint_manager
from core.environment_monitor import environment_monitor
from core.interrupt_override import interrupt_manager
from core.nondet_control import decision_logger
from core.plan_evolution import plan_evolution
from core.proactive_adaptation import adaptation_engine
from core.project_manager import project_manager
from core.project_state import ProjectState, delete_project, list_projects
from core.system_governor import system_governor
from core.system_identity import system_identity

logger = logging.getLogger("build_routes")
router = APIRouter(prefix="/api/build", tags=["Build"])


class BuildStartRequest(BaseModel):
    goal: str
    workspace: str | None = None
    auto_approve: bool = True


@router.post("/start")
async def start_build(req: BuildStartRequest):
    if not req.goal or len(req.goal.strip()) < 5:
        raise HTTPException(422, "Goal must be at least 5 characters")
    # Enqueue via project manager — process_queue background loop handles execution
    entry = project_manager.enqueue(req.goal)
    return {
        "name": entry.name,
        "status": "started",
        "goal": req.goal[:80],
    }


@router.get("/status/{project_name}")
async def get_build_status(project_name: str):
    status = build_service.get_status(project_name)
    if not status:
        state = ProjectState.load(project_name)
        if not state:
            raise HTTPException(404, "Project not found")
        from core.success_criteria import get_summary
        status = {
            "name": state.project_name,
            "status": state.status,
            "goal": state.goal[:80],
            "retries": state.retries,
            "issues": len(state.issues),
            "validation": get_summary(state) if state.validation_results else None,
            "quality_score": state.quality_score,
            "partial_progress": state.partial_progress,
        }
    return status


@router.post("/cancel/{project_name}")
async def cancel_build(project_name: str):
    ok = build_service.cancel(project_name)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"status": "cancelled", "project": project_name}


@router.get("/projects")
async def list_all_projects():
    return {"projects": list_projects()}


@router.get("/projects/{project_name}")
async def get_project(project_name: str):
    state = ProjectState.load(project_name)
    if not state:
        raise HTTPException(404, "Project not found")
    from core.success_criteria import get_summary
    return {
        "name": state.project_name,
        "goal": state.goal[:200],
        "status": state.status,
        "retries": state.retries,
        "plan": state.plan,
        "issues": state.issues[:20],
        "validation": get_summary(state) if state.validation_results else None,
        "events": state.events[-20:],
        "agent_log": state.agent_log[-20:],
        "created_at": state.created_at,
    }


@router.delete("/projects/{project_name}")
async def remove_project(project_name: str):
    ok = delete_project(project_name)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"status": "deleted", "project": project_name}


@router.post("/queue")
async def enqueue_goal(req: BuildStartRequest):
    entry = project_manager.enqueue(req.goal)
    return {
        "name": entry.name,
        "status": entry.status,
        "priority": entry.priority,
        "goal": entry.goal[:80],
    }


@router.get("/queue")
async def list_queue():
    return {"projects": project_manager.list_all()}


@router.post("/queue/pause/{project_name}")
async def pause_project(project_name: str):
    ok = project_manager.pause(project_name)
    if not ok:
        raise HTTPException(404, "Project not found or not running")
    return {"status": "paused", "project": project_name}


@router.post("/queue/resume/{project_name}")
async def resume_project(project_name: str):
    ok = project_manager.resume(project_name)
    if not ok:
        raise HTTPException(404, "Project not found or not paused")
    return {"status": "resumed", "project": project_name}


@router.post("/queue/cancel/{project_name}")
async def cancel_project(project_name: str):
    ok = project_manager.cancel(project_name)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"status": "cancelled", "project": project_name}


@router.post("/queue/priority/{project_name}")
async def set_priority(project_name: str, priority: int = 1):
    ok = project_manager.set_priority(project_name, priority)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"status": "priority_set", "project": project_name, "priority": priority}


class ServiceCommand(BaseModel):
    action: str  # start | stop | install | uninstall | status


@router.post("/daemon")
async def daemon_command(req: ServiceCommand):
    try:
        from daemon.jarvis_service import JarvisDaemon
        daemon = JarvisDaemon()
        action = req.action.lower()
        if action == "start":
            daemon.start()
            return {"status": "started"}
        elif action == "stop":
            daemon.stop()
            return {"status": "stopped"}
        elif action == "install":
            JarvisDaemon.install()
            return {"status": "installed"}
        elif action == "uninstall":
            JarvisDaemon.uninstall()
            return {"status": "uninstalled"}
        elif action == "status":
            JarvisDaemon.status()
            return {"status": "checked"}
        else:
            raise HTTPException(422, f"Unknown action: {action}")
    except Exception as e:
        raise HTTPException(500, f"Daemon command failed: {e}")


# ── Phase 5: Environment Monitor ──

@router.get("/environment")
async def get_environment():
    snap = environment_monitor.check(force=True)
    return snap.to_dict()


@router.get("/environment/summary")
async def get_env_summary():
    return {"summary": environment_monitor.summary()}


@router.get("/adaptation")
async def get_adaptation():
    actions = adaptation_engine.assess()
    rules = adaptation_engine.get_rules_triggered()
    return {"actions": actions, "rules_triggered": rules}


@router.post("/adaptation/reset")
async def reset_adaptation():
    adaptation_engine.reset_counters()
    return {"status": "reset"}


# ── Phase 4: System Identity ──

@router.get("/identity")
async def get_identity():
    return system_identity.get().to_dict()


@router.get("/governor/history/{project_name}")
async def get_governor_history(project_name: str):
    history = system_governor.get_history(project_name)
    return {
        "project": project_name,
        "decisions": [{"action": d.action, "reason": d.reason,
                        "confidence": d.confidence, "details": d.details}
                       for d in history],
    }


@router.get("/evolution/mutations/{project_name}")
async def get_mutations(project_name: str):
    mutations = plan_evolution.get_mutations(project_name)
    return {
        "project": project_name,
        "mutations": [{"type": m.mutation_type, "reason": m.reason,
                        "target": m.target_task_id, "retry": m.applied_at_retry}
                       for m in mutations],
    }


# ── Phase 3: Interrupt / Override ──

@router.post("/interrupt/{project_name}")
async def interrupt_build(project_name: str):
    interrupt_manager.signal_pause(project_name)
    return {"status": "interrupt_signaled", "project": project_name}


@router.post("/cancel/{project_name}")
async def cancel_build_alt(project_name: str):
    ok = build_service.cancel(project_name)
    if not ok:
        raise HTTPException(404, "Project not found or already done")
    return {"status": "cancel_signaled", "project": project_name}


@router.post("/override/{project_name}")
async def override_build(project_name: str, overrides: dict):
    ok = build_service.override(project_name, overrides)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"status": "override_applied", "project": project_name, "overrides": overrides}


@router.post("/resume/{project_name}")
async def resume_build(project_name: str):
    ok = build_service.resume(project_name)
    if not ok:
        raise HTTPException(404, "Project not found or not paused")
    return {"status": "resumed", "project": project_name}


# ── Phase 3: Checkpoints ──

@router.get("/checkpoints/{project_name}")
async def list_checkpoints(project_name: str):
    cps = checkpoint_manager.list_checkpoints(project_name)
    return {"project": project_name, "checkpoints": cps}


@router.post("/checkpoints/rollback/{project_name}/{step_id}")
async def rollback_checkpoint(project_name: str, step_id: str):
    from pathlib import Path
    ws = Path.cwd() / project_name
    ok = checkpoint_manager.rollback(project_name, step_id, ws)
    if not ok:
        raise HTTPException(404, f"Checkpoint not found: {project_name}/{step_id}")
    return {"status": "rolled_back", "project": project_name, "step": step_id}


# ── Phase 3: Decision Log ──

@router.get("/decisions/{project_name}")
async def get_decision_log(project_name: str):
    entries = decision_logger.get_log(project_name)
    seed = decision_logger.get_seed(project_name)
    replay = decision_logger.replay_mode(project_name)
    return {
        "project": project_name,
        "seed": seed,
        "replay_mode": replay,
        "decisions": [e.to_dict() for e in entries],
    }
