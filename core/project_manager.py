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
"""core/project_manager.py
Manages multiple concurrent JARVIS projects — queue, priorities,
checkpoint/resume, workers.
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("project_manager")

from core.build.service import build_service
from core.project_state import ProjectState, list_projects


@dataclass
class ProjectEntry:
    name: str
    goal: str
    priority: int = 1
    status: str = "queued"
    created_at: str = ""
    stopped_at: str = ""
    error: str = ""
    task: asyncio.Task | None = None


MANAGER_STATE_PATH = Path.home() / ".jarvis" / "manager_state.json"
DEFAULT_MAX_WORKERS = 2


class ProjectManager:
    """Multi-project queue with priorities, concurrent limits, and lifecycle."""

    def __init__(self, max_workers: int = DEFAULT_MAX_WORKERS):
        self.max_workers = max_workers
        self._projects: dict[str, ProjectEntry] = {}
        self._queue: list[str] = []
        self._running: set[str] = set()
        self._load_state()

    def _load_state(self):
        if MANAGER_STATE_PATH.exists():
            try:
                data = json.loads(MANAGER_STATE_PATH.read_text(encoding="utf-8"))
                for item in data.get("projects", []):
                    entry = ProjectEntry(**item)
                    self._projects[entry.name] = entry
                    if entry.status == "running":
                        entry.status = "paused"  # Don't auto-resume without daemon
                        self._queue.append(entry.name)
            except Exception as e:
                logger.error(f"[MANAGER] State load error: {e}")

    def _save_state(self):
        MANAGER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "projects": [
                {"name": e.name, "goal": e.goal, "priority": e.priority,
                 "status": e.status, "created_at": e.created_at, "error": e.error}
                for e in self._projects.values()
            ]
        }
        MANAGER_STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def enqueue(self, goal: str, priority: int = 1) -> ProjectEntry:
        """Add a new project to the queue."""
        safe_name = re.sub(r'[^a-zA-Z0-9_-]+', '_', goal)[:40].strip("_").lower() or "project"
        if safe_name in self._projects:
            existing = self._projects[safe_name]
            if existing.status in ("running", "queued"):
                logger.info(f"[MANAGER] Project {safe_name} already {existing.status}")
                return existing

        entry = ProjectEntry(
            name=safe_name, goal=goal, priority=priority,
            status="queued", created_at=datetime.now().isoformat(),
        )
        self._projects[safe_name] = entry
        self._queue.append(safe_name)
        self._queue.sort(key=lambda n: self._projects[n].priority, reverse=True)
        self._save_state()
        logger.info(f"[MANAGER] Enqueued {safe_name} (priority {priority})")
        return entry

    async def process_queue(self):
        """Continuously process queue up to max_workers."""
        while True:
            available = self.max_workers - len(self._running)
            while available > 0 and self._queue:
                name = self._queue.pop(0)
                if name in self._running:
                    continue
                entry = self._projects[name]
                if entry.status in ("done", "failed", "cancelled"):
                    continue
                entry.status = "running"
                self._running.add(name)
                self._save_state()
                entry.task = asyncio.create_task(self._run_project(name))
                available -= 1

            if not self._running and not self._queue:
                await asyncio.sleep(1)
                continue

            done_tasks = [n for n in self._running if self._projects[n].task and self._projects[n].task.done()]
            for name in done_tasks:
                self._running.discard(name)

            await asyncio.sleep(0.5)

    async def _run_project(self, name: str):
        """Execute a single project using BuildService."""
        from core.build.service import build_service
        entry = self._projects[name]
        try:
            # Enqueue and run via BuildService
            build_entry = build_service.enqueue(entry.goal)
            await build_service._run_project(build_entry.name)
            # Load the final state
            from core.project_state import ProjectState
            state = ProjectState.load(build_entry.name)
            entry.status = state.status if state else "failed"
            entry.error = ""
            logger.info(f"[MANAGER] {name} completed: {entry.status}")
        except Exception as e:
            entry.status = "failed"
            entry.error = str(e)[:200]
            logger.error(f"[MANAGER] {name} failed: {e}")
        finally:
            entry.stopped_at = datetime.now().isoformat()
            self._running.discard(name)
            self._save_state()

    def pause(self, name: str) -> bool:
        """Pause a running project."""
        entry = self._projects.get(name)
        if not entry or entry.status != "running":
            return False
        if entry.task:
            entry.task.cancel()
        entry.status = "paused"
        self._running.discard(name)
        state = ProjectState.load(name)
        if state:
            state.log_event("paused", {})
        self._save_state()
        return True

    def resume(self, name: str) -> bool:
        """Resume a paused project."""
        entry = self._projects.get(name)
        if not entry or entry.status not in ("paused", "fixing"):
            return False
        entry.status = "queued"
        self._queue.append(name)
        state = ProjectState.load(name)
        if state:
            state.log_event("resumed", {})
        self._save_state()
        return True

    def cancel(self, name: str) -> bool:
        """Cancel a project entirely."""
        entry = self._projects.get(name)
        if not entry:
            return False
        if entry.task:
            entry.task.cancel()
        entry.status = "cancelled"
        self._running.discard(name)
        self._queue = [n for n in self._queue if n != name]
        state = ProjectState.load(name)
        if state:
            state.status = "cancelled"
            state.log_event("cancelled", {})
            state.save()
        self._save_state()
        return True

    def remove(self, name: str) -> bool:
        self.cancel(name)
        self._projects.pop(name, None)
        self._save_state()
        return True

    def set_priority(self, name: str, priority: int) -> bool:
        entry = self._projects.get(name)
        if not entry:
            return False
        entry.priority = priority
        if name in self._queue:
            self._queue.sort(key=lambda n: self._projects[n].priority, reverse=True)
        self._save_state()
        return True

    def get_status(self, name: str) -> dict | None:
        """Get detailed status of a project."""
        entry = self._projects.get(name)
        if not entry:
            state = ProjectState.load(name)
            if state:
                from core.success_criteria import get_summary
                return {
                    "name": state.project_name,
                    "goal": state.goal[:80],
                    "status": state.status,
                    "retries": state.retries,
                    "issues": len(state.issues),
                    "validation": get_summary(state) if state.validation_results else None,
                }
            return None
        return {
            "name": entry.name,
            "goal": entry.goal[:80],
            "status": entry.status,
            "priority": entry.priority,
            "created_at": entry.created_at,
            "error": entry.error[:100] if entry.error else "",
        }

    def list_all(self) -> list[dict]:
        """List all projects with status."""
        projects = {p["name"]: p for p in list_projects()}
        for entry in self._projects.values():
            if entry.name not in projects:
                projects[entry.name] = {
                    "name": entry.name, "status": entry.status,
                    "goal": entry.goal[:80], "priority": entry.priority,
                }
            else:
                projects[entry.name]["priority"] = entry.priority
        result = sorted(projects.values(), key=lambda p: p.get("priority", 0), reverse=True)

        for r in result:
            if r["name"] in self._running:
                r["status"] = "running"
            elif r["name"] in self._queue:
                r["status"] = "queued"

        return result


project_manager = ProjectManager()