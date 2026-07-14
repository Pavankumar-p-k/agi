import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "../../data")

_BUILD_LOOP: Any = None
_GOAL_MANAGER: Any = None
_MEMORY_MANAGER: Any = None

_BUILD_EXECUTIONS: dict[str, asyncio.Task] = {}


async def _ensure_automation(project_dir: str = ""):
    global _BUILD_LOOP, _GOAL_MANAGER, _MEMORY_MANAGER
    if _BUILD_LOOP is not None:
        return
    from core.planner.unified_store import UnifiedStore
    from brain.automation.loop import AutomationLoop

    _GOAL_MANAGER = UnifiedStore()
    _MEMORY_MANAGER = None  # uses MemoryFacade via AutomationLoop default
    _BUILD_LOOP = AutomationLoop(
        goal_manager=_GOAL_MANAGER,
        project_dir=str(Path(project_dir).resolve()) if project_dir else "",
    )


async def _emit_progress(progress_cb, phase: str, detail: str, elapsed_s: float = 0.0):
    if not progress_cb:
        return
    try:
        await progress_cb({
            "elapsed_s": elapsed_s,
            "phase": phase,
            "detail": detail,
        })
    except Exception as e:
        logger.debug("progress callback failed: %s", e)


async def do_build_project(task: str, project_dir: str, progress_cb: Callable[[dict], Awaitable[None]] | None = None, **kwargs) -> dict:
    _start = time.time()
    await _ensure_automation(project_dir)
    goal = _GOAL_MANAGER.create(goal=task, priority=10, tags=["build"])
    await _emit_progress(progress_cb, "plan", f"Created build goal: {task[:80]}")

    await _BUILD_LOOP._build_project(goal)
    g = _GOAL_MANAGER.get(goal.id)
    status = g.status.value if g else "unknown"
    elapsed = round(time.time() - _start, 1)
    await _emit_progress(progress_cb, status, f"Completed in {elapsed}s", elapsed)

    return {
        "success": status == "completed",
        "status": status,
        "objective": task,
        "project_dir": str(Path(project_dir).resolve()),
        "completion": _BUILD_LOOP._completion if _BUILD_LOOP else 0.0,
        "build_history": list(_BUILD_LOOP._build_history.values()) if _BUILD_LOOP else [],
        "elapsed_s": elapsed,
    }


async def do_repair_project(project_dir: str, build_output: str = "", progress_cb: Callable[[dict], Awaitable[None]] | None = None, **kwargs) -> dict:
    _start = time.time()
    await _ensure_automation(project_dir)
    analysis = {"errors": [{"fix": build_output}]} if build_output else {"summary": "Repair requested"}
    await _emit_progress(progress_cb, "repair", f"Starting repair in {project_dir}")

    ok = await _BUILD_LOOP._repair("Repair build", str(Path(project_dir).resolve()), analysis)
    elapsed = round(time.time() - _start, 1)
    await _emit_progress(progress_cb, "done" if ok else "failed", f"Repair {'succeeded' if ok else 'failed'} in {elapsed}s", elapsed)

    return {
        "success": ok,
        "project_dir": str(Path(project_dir).resolve()),
        "elapsed_s": elapsed,
    }


async def do_run_tests(project_dir: str, progress_cb: Callable[[dict], Awaitable[None]] | None = None, **kwargs) -> dict:
    _start = time.time()
    await _ensure_automation(project_dir)
    plan = {"test_command": kwargs.get("test_command", "")}
    goal_id = _GOAL_MANAGER.create(goal="Run tests", priority=0, tags=["test"]).id if _GOAL_MANAGER else ""
    await _emit_progress(progress_cb, "test", f"Running tests in {project_dir}")

    passed = await _BUILD_LOOP._phase_test("Run tests", str(Path(project_dir).resolve()), plan.get("test_command", ""), goal_id)
    elapsed = round(time.time() - _start, 1)
    await _emit_progress(progress_cb, "done", f"Tests {'passed' if passed else 'failed'} in {elapsed}s", elapsed)

    return {
        "success": passed,
        "project_dir": str(Path(project_dir).resolve()),
        "elapsed_s": elapsed,
    }


async def do_runtime_validate(project_dir: str, progress_cb: Callable[[dict], Awaitable[None]] | None = None, **kwargs) -> dict:
    _start = time.time()
    await _ensure_automation(project_dir)
    plan = {}
    goal_id = _GOAL_MANAGER.create(goal="Runtime validate", priority=0, tags=["validate"]).id if _GOAL_MANAGER else ""
    await _emit_progress(progress_cb, "validate", f"Running runtime validation in {project_dir}")

    valid = await _BUILD_LOOP._phase_runtime_validation("Validate", str(Path(project_dir).resolve()), plan, goal_id)
    elapsed = round(time.time() - _start, 1)
    await _emit_progress(progress_cb, "done", f"Validation {'passed' if valid else 'failed'} in {elapsed}s", elapsed)

    return {
        "success": valid,
        "project_dir": str(Path(project_dir).resolve()),
        "elapsed_s": elapsed,
    }


async def cancel_build(execution_id: str, **kwargs) -> dict:
    task = _BUILD_EXECUTIONS.pop(execution_id, None)
    if task:
        task.cancel()
        return {"cancelled": True, "execution_id": execution_id}
    return {"cancelled": False, "execution_id": execution_id, "error": "Not found"}
