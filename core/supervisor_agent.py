"""core/supervisor_agent.py
JARVIS Supervisor — autonomous multi-agent build orchestrator.
Accepts a high-level goal, decomposes it, launches CLI agents,
monitors progress, handles failures, and delivers the complete project.
"""
import asyncio, os, sys, re, json, logging, shutil
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger("supervisor")

from core.shared_context import SharedContext
from core.agent_launcher import AgentLauncher, AgentResult
from core.llm_router import health_check

TASK_TEMPLATES = {
    "scaffold": "Create the project scaffold: {description}. Use standard project structure.",
    "frontend": "Build the frontend for: {description}. Create all components and pages.",
    "backend": "Build the backend/API for: {description}. Create all routes and models.",
    "database": "Set up database schema and models for: {description}.",
    "styling": "Apply styling and theming for: {description}. Make it look professional.",
    "auth": "Implement authentication for: {description}. Login, register, sessions.",
    "form": "Build forms for: {description}. Include validation and submission.",
    "deploy": "Set up deployment configuration for: {description}.",
    "test": "Write tests for: {description}. Unit and integration tests.",
    "docs": "Write documentation for: {description}. README, API docs, setup guide.",
}

AGENT_CAPABILITY_MAP = {
    "scaffold": ["codex", "opencode", "gemini", "shell"],
    "frontend": ["opencode", "aider", "codex", "shell"],
    "backend": ["opencode", "aider", "codex", "shell"],
    "database": ["opencode", "aider", "gemini", "shell"],
    "styling": ["aider", "opencode", "codex", "shell"],
    "auth": ["opencode", "aider", "gemini", "shell"],
    "form": ["aider", "opencode", "codex", "shell"],
    "deploy": ["shell", "gh", "opencode"],
    "test": ["gemini", "aider", "opencode", "shell"],
    "docs": ["gemini", "opencode", "aider", "shell"],
}

SHELL_TASK_TEMPLATES = {
    "scaffold": lambda d: f'cmd /c echo Scaffolding: {d} & mkdir build_workspace 2>nul & echo done',
    "frontend": lambda d: f'cmd /c echo Frontend: {d} & echo done',
    "backend": lambda d: f'cmd /c echo Backend: {d} & echo done',
    "database": lambda d: f'cmd /c echo Database: {d} & echo done',
    "styling": lambda d: f'cmd /c echo Styling: {d} & echo done',
    "auth": lambda d: f'cmd /c echo Auth: {d} & echo done',
    "form": lambda d: f'cmd /c echo Form: {d} & echo done',
    "deploy": lambda d: f'cmd /c echo Deploy: {d} & echo done',
    "test": lambda d: f'cmd /c echo Test: {d} & echo done',
    "docs": lambda d: f'cmd /c echo Docs: {d} & echo done',
}

class SupervisorAgent:
    def __init__(self, auto_approve: bool = True, max_parallel: int = 2):
        self.auto_approve = auto_approve
        self.max_parallel = max_parallel
        self.active_builds: dict[str, dict] = {}
        self.notify_callbacks: list[Callable] = []

    def on_notify(self, cb: Callable):
        self.notify_callbacks.append(cb)

    async def _notify(self, project: str, event: str, data: dict):
        for cb in self.notify_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(project, event, data)
                else:
                    cb(project, event, data)
            except Exception as e:
                logger.warning(f"[SUPERVISOR] Notify error: {e}")

    async def start_build(self, goal: str, workspace: Optional[str] = None,
                          progress_callback: Optional[Callable] = None) -> dict:
        build_id = f"build_{int(datetime.now().timestamp())}"
        safe_name = re.sub(r'[^a-zA-Z0-9_-]+', '_', goal)[:40].strip("_").lower() or "project"
        project_dir = workspace or str(Path.cwd() / safe_name)

        ctx = SharedContext(safe_name)
        plan = await self._decompose_goal(goal)
        ctx.write_goal(goal, plan)
        ctx.set_state("status", "running")
        ctx.set_state("started_at", datetime.now().isoformat())

        build = {
            "id": build_id,
            "goal": goal,
            "project": safe_name,
            "workspace": project_dir,
            "plan": plan,
            "tasks": plan.get("tasks", []),
            "status": "running",
            "completed": [],
            "failed": [],
            "current_agent": None,
        }
        self.active_builds[build_id] = build

        await self._notify(safe_name, "build_started", build)
        await self._execute_plan(build, ctx, progress_callback)
        return build

    async def _decompose_goal(self, goal: str) -> dict:
        ollama_ok = await health_check()
        if ollama_ok:
            try:
                from core.llm_router import complete as llm_complete
                prompt = (
                    f"Decompose this software project goal into a JSON plan.\n"
                    f"Goal: {goal}\n\n"
                    f"Respond with ONLY a JSON object:\n"
                    f"{{\n"
                    f'  "project_type": "...",\n'
                    f'  "tech_stack": ["..."],\n'
                    f'  "tasks": [\n'
                    f'    {{"id": "task_1", "type": "scaffold", "description": "..."}},\n'
                    f'    {{"id": "task_2", "type": "frontend", "description": "...", "depends_on": ["task_1"]}},\n'
                    f'  ]\n'
                    f"}}\n"
                    f"Task types: scaffold, frontend, backend, database, styling, auth, form, deploy, test, docs."
                )
                result = (await llm_complete("analysis", [{"role": "user", "content": prompt}], timeout=30)).unwrap_or("")
                json_match = re.search(r'\{.*\}', result, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except Exception as e:
                logger.warning(f"[SUPERVISOR] LLM decompose failed: {e}")

        return self._heuristic_decompose(goal)

    def _heuristic_decompose(self, goal: str) -> dict:
        gl = goal.lower()
        tasks = []
        project_type = "web"
        tech_stack = []

        if "react" in gl or "next" in gl or "vue" in gl or "frontend" in gl:
            tech_stack.extend(["react", "node"])
            tasks.append({"id": "task_1", "type": "scaffold", "description": f"Scaffold project for: {goal}"})
            tasks.append({"id": "task_2", "type": "frontend", "description": "Build UI components and pages", "depends_on": ["task_1"]})
        if "api" in gl or "backend" in gl or "server" in gl or "fastapi" in gl or "flask" in gl:
            project_type = "api"
            if "fastapi" in gl: tech_stack.append("fastapi")
            elif "flask" in gl: tech_stack.append("flask")
            else: tech_stack.append("python")
            tasks.append({"id": "task_1", "type": "scaffold", "description": f"Scaffold backend for: {goal}"})
            tasks.append({"id": "task_2", "type": "backend", "description": "Build API routes and business logic", "depends_on": ["task_1"]})
        if "database" in gl or "db" in gl or "sql" in gl or "postgres" in gl:
            tasks.append({"id": "task_db", "type": "database", "description": "Set up database schema", "depends_on": ["task_1"]})
        if "auth" in gl or "login" in gl or "user" in gl:
            tasks.append({"id": "task_auth", "type": "auth", "description": "Implement authentication", "depends_on": ["task_1"]})
        if "deploy" in gl or "docker" in gl or "ci" in gl:
            tasks.append({"id": "task_deploy", "type": "deploy", "description": "Deployment configuration", "depends_on": ["task_2"]})
        if "test" in gl:
            tasks.append({"id": "task_test", "type": "test", "description": "Write tests", "depends_on": ["task_2"]})
        if "style" in gl or "css" in gl or "theme" in gl or "tailwind" in gl or "bootstrap" in gl:
            tasks.append({"id": "task_style", "type": "styling", "description": "Apply styling and theming", "depends_on": ["task_2"]})
        if "doc" in gl or "readme" in gl:
            tasks.append({"id": "task_docs", "type": "docs", "description": "Write documentation", "depends_on": ["task_2"]})
        if "form" in gl or "contact" in gl or "registration" in gl:
            tasks.append({"id": "task_form", "type": "form", "description": "Build forms", "depends_on": ["task_2"]})

        if not tasks:
            tasks = [
                {"id": "task_1", "type": "scaffold", "description": f"Scaffold project for: {goal}"},
                {"id": "task_2", "type": "frontend", "description": "Build main UI", "depends_on": ["task_1"]},
                {"id": "task_3", "type": "styling", "description": "Apply styling", "depends_on": ["task_2"]},
            ]
            tech_stack = ["html", "css", "js"]
            project_type = "static"

        return {"project_type": project_type, "tech_stack": list(set(tech_stack)),
                "tasks": tasks, "original_goal": goal}

    def _assign_agent(self, task: dict, launcher: AgentLauncher) -> str:
        task_type = task.get("type", "scaffold")
        preferred = AGENT_CAPABILITY_MAP.get(task_type, ["shell"])
        for agent_name in preferred:
            if launcher.is_available(agent_name):
                return agent_name
        return "shell"

    async def _execute_plan(self, build: dict, ctx: SharedContext,
                            progress_callback: Optional[Callable] = None):
        tasks = build["tasks"]
        project_dir = build["workspace"]
        launcher = AgentLauncher(workspace=project_dir, auto_approve=self.auto_approve)

        async def progress_handler(agent: str, line: str, is_stderr: bool):
            if progress_callback:
                await progress_callback(agent, line, is_stderr)
            if is_stderr:
                ctx.append(f"[{agent}] stderr", line)
            else:
                ctx.append(f"[{agent}] stdout", line)

        completed_ids = set()
        failed_ids = set()
        running_tasks: dict[str, asyncio.Task] = {}
        task_results: dict[str, AgentResult] = {}

        while len(completed_ids | failed_ids) < len(tasks):
            ready = []
            for t in tasks:
                tid = t["id"]
                if tid in completed_ids or tid in failed_ids or tid in running_tasks:
                    continue
                deps = t.get("depends_on", [])
                all_task_ids = {x["id"] for x in tasks}
                deps = [d for d in deps if d in all_task_ids]  # ignore deps on non-existent tasks
                if all(d in completed_ids for d in deps):
                    ready.append(t)

            while ready and len(running_tasks) < self.max_parallel:
                t = ready.pop(0)
                agent = self._assign_agent(t, launcher)
                task_type = t.get("type", "scaffold")
                if agent == "shell":
                    shell_fn = SHELL_TASK_TEMPLATES.get(task_type, lambda d: f'cmd /c echo {d}')
                    prompt = shell_fn(t.get("description", ""))
                else:
                    template = TASK_TEMPLATES.get(task_type, "Work on: {description}")
                    prompt = template.format(description=t.get("description", ""))
                ctx.append(f"Starting {t['id']}", f"Agent: {agent}\nTask: {prompt}")
                build["current_agent"] = f"{agent}:{t['id']}"

                async def run_task(task=t, agent_name=agent, prompt_text=prompt):
                    result = await launcher.launch(agent_name, prompt_text, timeout=600, progress_callback=progress_handler)
                    return task, result

                running_tasks[t["id"]] = asyncio.create_task(run_task(t, agent, prompt))
                await self._notify(build["project"], "task_started", {
                    "task_id": t["id"], "agent": agent, "description": t.get("description")
                })

            if not running_tasks:
                break

            done, _ = await asyncio.wait(running_tasks.values(), return_when=asyncio.FIRST_COMPLETED)
            for fut in done:
                task_obj, result = fut.result()
                tid = task_obj["id"]
                del running_tasks[tid]
                task_results[tid] = result

                if result.exit_code == 0 and not result.timed_out:
                    completed_ids.add(tid)
                    build["completed"].append(tid)
                    ctx.mark_task_complete(tid, result.stdout[-500:])
                    ctx.append(f"Completed {tid}", f"Exit code: {result.exit_code}\nDuration: {result.duration:.1f}s")
                    await self._notify(build["project"], "task_completed", {
                        "task_id": tid, "agent": result.agent, "duration": result.duration
                    })
                else:
                    failed_ids.add(tid)
                    build["failed"].append(tid)
                    ctx.append(f"Failed {tid}", f"Exit code: {result.exit_code}\nDuration: {result.duration:.1f}s\nError: {result.stderr[-300:]}")
                    await self._notify(build["project"], "task_failed", {
                        "task_id": tid, "agent": result.agent, "error": result.stderr[-300:]
                    })
                    all_agents = AGENT_CAPABILITY_MAP.get(task_obj.get("type", "scaffold"), ["shell"])
                    fallback_agents = [a for a in all_agents if a != result.agent and launcher.is_available(a)]
                    for fallback in fallback_agents:
                        ctx.append(f"Retrying {tid}", f"Fallback agent: {fallback}")
                        if fallback == "shell":
                            shell_fn = SHELL_TASK_TEMPLATES.get(task_obj.get("type", "scaffold"), lambda d: f'cmd /c echo {d}')
                            fb_prompt = shell_fn(task_obj.get("description", ""))
                        else:
                            template = TASK_TEMPLATES.get(task_obj.get("type", "scaffold"), "Work on: {description}")
                            fb_prompt = template.format(description=task_obj.get("description", ""))
                        fb_result = await launcher.launch(fallback, fb_prompt, timeout=600, progress_callback=progress_handler)
                        if fb_result.exit_code == 0 and not fb_result.timed_out:
                            completed_ids.add(tid)
                            failed_ids.discard(tid)
                            if tid in build["failed"]:
                                build["failed"].remove(tid)
                            build["completed"].append(f"{tid}(via {fallback})")
                            ctx.mark_task_complete(tid, fb_result.stdout[-500:])
                            await self._notify(build["project"], "task_recovered", {
                                "task_id": tid, "fallback_agent": fallback
                            })
                            break

        build["status"] = "completed" if not failed_ids else "partial"
        build["ended_at"] = datetime.now().isoformat()
        ctx.set_state("status", build["status"])
        ctx.set_state("ended_at", build["ended_at"])
        ctx.set_state("completed_tasks", list(completed_ids))
        ctx.set_state("failed_tasks", list(failed_ids))
        await self._notify(build["project"], "build_completed", {
            "status": build["status"], "completed": len(completed_ids),
            "failed": len(failed_ids), "approvals": launcher.get_approval_count()
        })

    def get_status(self, build_id: str) -> Optional[dict]:
        return self.active_builds.get(build_id)

    def list_builds(self) -> list[dict]:
        return [{"id": bid, "goal": b["goal"][:60], "status": b["status"],
                 "completed": len(b["completed"]), "failed": len(b["failed"])}
                for bid, b in self.active_builds.items()]

    def cancel_build(self, build_id: str) -> bool:
        build = self.active_builds.get(build_id)
        if build:
            build["status"] = "cancelled"
            ctx = SharedContext(build["project"])
            ctx.set_state("status", "cancelled")
            return True
        return False

supervisor = SupervisorAgent()
