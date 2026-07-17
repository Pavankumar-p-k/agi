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


async def do_build_apk(project_dir: str, progress_cb: Callable[[dict], Awaitable[None]] | None = None, **kwargs) -> dict:
    """Build an Android APK from a project directory.
    
    Args:
        project_dir: Path to the Android project directory
        progress_cb: Optional progress callback
        
    Returns:
        Dict with success status, APK path, and build details
    """
    import shutil
    _start = time.time()
    await _ensure_automation(project_dir)
    
    project_path = Path(project_dir).resolve()
    gradle_wrapper = project_path / "gradlew"
    gradle_wrapper_bat = project_path / "gradlew.bat"
    
    if not (gradle_wrapper.exists() or gradle_wrapper_bat.exists()):
        # Check for build.gradle to see if it's an Android project
        build_gradle = project_path / "build.gradle"
        build_gradle_kts = project_path / "build.gradle.kts"
        if not (build_gradle.exists() or build_gradle_kts.exists()):
            return {
                "success": False,
                "error": "No Gradle wrapper or build.gradle found. Not an Android project.",
                "project_dir": str(project_path),
            }
    
    await _emit_progress(progress_cb, "prepare", f"Preparing APK build in {project_dir}")
    
    # Ensure gradlew is executable
    if gradle_wrapper.exists():
        os.chmod(gradle_wrapper, 0o755)
    
    # Build APK
    await _emit_progress(progress_cb, "build", "Building APK...")
    
    gradle_cmd = "./gradlew assembleDebug" if gradle_wrapper.exists() else "gradlew.bat assembleDebug"
    
    try:
        # Use the existing build service
        from core.build.service import build_service
        entry = build_service.enqueue(f"Build APK for {project_dir}")
        
        # Run gradle assembleDebug
        proc = await asyncio.create_subprocess_shell(
            gradle_cmd,
            cwd=str(project_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        
        elapsed = round(time.time() - _start, 1)
        
        if proc.returncode != 0:
            error_msg = stderr.decode() if stderr else "Build failed"
            await _emit_progress(progress_cb, "failed", f"Build failed: {error_msg[:200]}")
            return {
                "success": False,
                "error": error_msg[:500],
                "project_dir": str(project_path),
                "elapsed_s": elapsed,
            }
        
        # Find generated APK
        apk_files = list(project_path.rglob("*.apk"))
        if not apk_files:
            await _emit_progress(progress_cb, "failed", "No APK generated")
            return {
                "success": False,
                "error": "Build succeeded but no APK found",
                "project_dir": str(project_path),
                "elapsed_s": elapsed,
            }
        
        # Get the most recent debug APK
        debug_apks = [f for f in apk_files if "debug" in f.name.lower()]
        apk_path = debug_apks[0] if debug_apks else apk_files[0]
        
        elapsed = round(time.time() - _start, 1)
        await _emit_progress(progress_cb, "done", f"APK built: {apk_path.name}", elapsed)
        
        return {
            "success": True,
            "apk_path": str(apk_path),
            "apk_name": apk_path.name,
            "project_dir": str(project_path),
            "elapsed_s": elapsed,
        }
        
    except asyncio.TimeoutError:
        elapsed = round(time.time() - _start, 1)
        return {
            "success": False,
            "error": "Build timed out after 10 minutes",
            "project_dir": str(project_path),
            "elapsed_s": elapsed,
        }
    except Exception as e:
        elapsed = round(time.time() - _start, 1)
        logger.error(f"[BUILD] APK build failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_dir": str(project_path),
            "elapsed_s": elapsed,
        }
