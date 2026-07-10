"""AgentOrchestrator — wires sub-agents and automation loop into a unified coding agent.

Provides:
- `code(task, path)` — plan → generate → build → test → repair → verify
- `build(path)` — build existing project, auto-repair on failure
- `run(path)` — detect build system and run
- `understand(path)` — full repository analysis
"""
from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from core.storage import SYSTEM_DB
from core.workspace_manager import WorkspaceManager, ProjectMap
from core.repository_analyzer import RepositoryAnalyzer

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Unified orchestrator that wires sub-agents, automation loop, and repair pipeline."""

    def __init__(self, project_dir: str | None = None):
        self.project_dir = project_dir or os.getcwd()
        self.ws = WorkspaceManager(self.project_dir)
        self.analyzer = RepositoryAnalyzer(self.ws)
        self._loop = None
        self._goal_manager = None
        self._memory_manager = None

    async def _ensure_automation(self):
        """Lazy init automation loop with goal manager and memory."""
        if self._loop is not None:
            return
        from brain.goals.goal_manager import GoalManager
        from brain.memory.memory_manager import MemoryManager
        from brain.automation.loop import AutomationLoop

        self._goal_manager = GoalManager()
        self._memory_manager = MemoryManager()
        self._loop = AutomationLoop(
            goal_manager=self._goal_manager,
            memory_manager=self._memory_manager,
            project_dir=self.project_dir,
        )

    async def understand(self, path: str | None = None) -> dict:
        """Analyze and explain the repository."""
        if path:
            self.project_dir = str(Path(path).resolve())
            self.ws.set_path(self.project_dir)
            self.analyzer.set_path(self.project_dir)
        ws_info = self.ws.summary()
        explanation = self.analyzer.explain()
        return {
            "workspace": ws_info,
            "analysis": explanation,
            "import_graph": self.analyzer.build_import_graph(),
            "api_routes": self.analyzer.find_api_routes(),
            "dead_code_candidates": self.analyzer.find_dead_code(),
        }

    async def code(self, task: str, path: str | None = None) -> dict:
        """Execute a coding task autonomously: plan → generate → build → test → repair → verify."""
        if path:
            self.project_dir = str(Path(path).resolve())
            self.ws.set_path(self.project_dir)
            self.analyzer.set_path(self.project_dir)
        await self._ensure_automation()

        pm = self.ws.scan()
        logger.info("[Orchestrator] Starting coding task: %s in %s", task[:60], self.project_dir)

        # Create a goal for the automation loop
        goal = self._goal_manager.create(
            objective=task,
            priority=10,
            tags=["coding", pm.language, pm.build_system],
        )
        await self._loop.start()
        for _ in range(300):
            await asyncio.sleep(1)
            g = self._goal_manager.get(goal.id)
            if g and g.status.value in ("completed", "failed"):
                break
        await self._loop.stop()

        g = self._goal_manager.get(goal.id)
        result = {
            "task": task,
            "project_dir": self.project_dir,
            "status": g.status.value if g else "unknown",
            "build_history": self._loop._build_history if self._loop else {},
            "completion": self._loop._completion if self._loop else 0.0,
        }
        return result

    async def build(self, path: str | None = None, command: str | None = None) -> dict:
        """Build an existing project, auto-repair on failure."""
        if path:
            self.project_dir = str(Path(path).resolve())
            self.ws.set_path(self.project_dir)
            self.analyzer.set_path(self.project_dir)
        await self._ensure_automation()

        pm = self.ws.scan()
        build_cmd = command or pm.build_command
        if not build_cmd:
            return {"success": False, "error": "No build command detected for this project", "project": pm}

        logger.info("[Orchestrator] Building: %s with %s", self.project_dir, build_cmd)

        # Run build command directly
        build_result = await self._run_command(build_cmd, self.project_dir)

        if build_result["success"]:
            return build_result

        # Build failed — run repair loop
        logger.info("[Orchestrator] Build failed, running repair...")
        goal = self._goal_manager.create(
            objective=f"Fix build errors in {Path(self.project_dir).name}: {build_cmd}",
            priority=10,
            tags=["build-repair"],
        )
        await self._loop.start()
        for _ in range(300):
            await asyncio.sleep(1)
            g = self._goal_manager.get(goal.id)
            if g and g.status.value in ("completed", "failed"):
                break
        await self._loop.stop()

        # Final build attempt after repair
        result2 = await self._run_command(build_cmd, self.project_dir)

        return {
            "success": result2["success"],
            "output": result2["output"],
            "first_attempt": {"success": False, "output": result.output},
            "repaired": result2["success"],
            "duration_ms": result2["duration_ms"],
        }

    async def run(self, path: str | None = None) -> dict:
        """Run the project using detected run command."""
        if path:
            self.project_dir = str(Path(path).resolve())
            self.ws.set_path(self.project_dir)
        pm = self.ws.scan()
        run_cmd = pm.run_command
        if not run_cmd:
            # Fallback based on language
            if pm.language == "python":
                entry = pm.entry_points[0] if pm.entry_points else "main.py"
                run_cmd = f"python {entry}"
            elif pm.build_system == "cargo":
                run_cmd = "cargo run"
            elif pm.build_system == "go":
                run_cmd = "go run ."
            elif pm.package_manager in ("npm", "yarn"):
                run_cmd = "npm start"
            else:
                return {"success": False, "error": "No run command detected", "project": pm.summary()}

        logger.info("[Orchestrator] Running: %s", run_cmd)
        result = await self._run_command(run_cmd, self.project_dir)
        result["command"] = run_cmd
        return result

    async def workspace_status(self) -> dict:
        """Get current workspace status."""
        pm = self.ws.get_project_map()
        return {
            "root": pm.root,
            "git_root": pm.git_root,
            "branch": pm.active_branch,
            "language": pm.language,
            "framework": pm.framework,
            "build_system": pm.build_system,
            "package_manager": pm.package_manager,
            "files": len(pm.files),
            "entry_points": pm.entry_points,
            "test_suites": len(pm.test_suites),
            "build_command": pm.build_command,
            "test_command": pm.test_command,
            "run_command": pm.run_command,
        }

    async def project_summary(self) -> dict:
        """Get comprehensive project summary."""
        pm = self.ws.get_project_map()
        explanation = self.analyzer.explain()
        return {
            "name": Path(pm.root).name,
            "type": {
                "language": pm.language,
                "framework": pm.framework or "none",
                "build_system": pm.build_system,
                "package_manager": pm.package_manager,
            },
            "structure": {
                "files": len(pm.files),
                "folders": len(pm.folders),
                "entry_points": pm.entry_points,
                "test_suites": pm.test_suites,
            },
            "pipeline": explanation.get("build_pipeline", {}),
            "dependencies": pm.dependencies,
            "git": {
                "branch": pm.active_branch,
                "root": pm.git_root,
            },
        }

    async def show_structure(self, max_depth: int = 3) -> list[str]:
        """Show tree-like directory structure."""
        return self.ws.show_structure(max_depth=max_depth)

    async def analyze_repository(self, aspect: str = "all") -> dict:
        """Analyze a specific aspect of the repository."""
        aspects = {
            "imports": lambda: self.analyzer.build_import_graph(),
            "modules": lambda: self.analyzer.build_module_graph(),
            "entry_points": lambda: self.analyzer.find_entry_points(),
            "api_routes": lambda: self.analyzer.find_api_routes(),
            "tests": lambda: self.analyzer.find_tests(),
            "auth": lambda: self.analyzer.find_auth_code(),
            "database": lambda: self.analyzer.find_database_layer(),
            "dead_code": lambda: self.analyzer.find_dead_code(),
            "pipeline": lambda: self.analyzer.find_build_pipeline(),
        }
        if aspect == "all":
            results = {}
            for name, fn in aspects.items():
                try:
                    results[name] = fn()
                except Exception as e:
                    results[name] = {"error": str(e)}
            return results
        fn = aspects.get(aspect)
        if fn:
            return {aspect: fn()}
        return {"error": f"Unknown aspect: {aspect}. Available: {list(aspects.keys())}"}

    async def _run_command(self, command: str, cwd: str, timeout: int = 600) -> dict:
        """Run a shell command and return structured result."""
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *shlex.split(command),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            duration_ms = round((time.monotonic() - start) * 1000)
            return {
                "success": proc.returncode == 0,
                "output": stdout.decode("utf-8", errors="replace"),
                "error": stderr.decode("utf-8", errors="replace"),
                "exit_code": proc.returncode or 0,
                "duration_ms": duration_ms,
            }
        except asyncio.TimeoutError:
            duration_ms = round((time.monotonic() - start) * 1000)
            return {"success": False, "output": "", "error": f"Command timed out after {timeout}s", "exit_code": -1, "duration_ms": duration_ms, "timed_out": True}
        except Exception as e:
            duration_ms = round((time.monotonic() - start) * 1000)
            return {"success": False, "output": "", "error": str(e), "exit_code": -1, "duration_ms": duration_ms}
