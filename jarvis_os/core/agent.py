from __future__ import annotations

from typing import Any


class JarvisOS:
    def __init__(
        self,
        *,
        config: Any,
        memory: Any,
        models: Any,
        tools: Any,
        intent_engine: Any,
        reasoning: Any,
        planner: Any,
        executor: Any,
        reflection: Any,
        loop: Any,
        agents: Any,
        agent_runtime: Any,
        plugins: Any,
        self_improve: Any,
        jobs: Any,
        compat: Any,
        skills: Any,
        policy: Any,
        telemetry: Any,
        scheduler: Any,
        daemon: Any,
        monitor: Any,
        extensions_manager: Any = None,
        links_manager: Any = None,
    ) -> None:
        self.config = config
        self.memory = memory
        self.models = models
        self.tools = tools
        self.intent_engine = intent_engine
        self.reasoning = reasoning
        self.planner = planner
        self.executor = executor
        self.reflection = reflection
        self.loop = loop
        self.agents = agents
        self.agent_runtime = agent_runtime
        self.plugins = plugins
        self.self_improve = self_improve
        self.jobs = jobs
        self.compat = compat
        self.skills = skills
        self.policy = policy
        self.telemetry = telemetry
        self.scheduler = scheduler
        self.daemon = daemon
        self.monitor = monitor
        self._extensions_manager = extensions_manager
        self._links_manager = links_manager
        self.scheduler.bind_submitter(lambda prompt: self.submit_prompt(prompt, agent_name="auto"))
        self.daemon.bind_runner(self.run_due_schedules)

    @staticmethod
    def _safe_to_dict(value: Any) -> Any:
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict") and callable(value.to_dict):
            try:
                return value.to_dict()
            except Exception:
                return value
        return value

    def _prepare(self, prompt: str, context: dict[str, Any] | None = None, agent_name: str = "auto") -> dict[str, Any]:
        base_context = dict(context or {})
        preview = self.loop.preview(prompt, context=base_context)
        intent = preview["intent_obj"]
        intent_type = intent.get("type", "auto") if isinstance(intent, dict) else getattr(intent, "name", "auto")
        collaborators = self.agents.collaborate(intent_type, agent_name)
        specialist = collaborators[0]
        agent_context = self.agents.runtime_context(specialist.profile.name)
        merged_context = {**base_context, **agent_context}
        merged_context.setdefault("sandbox_root", str(self.config.workspace_root))
        preview = self.loop.preview(prompt, context=merged_context)
        analysis = preview["analysis"]
        plan = specialist.plan(prompt, intent, analysis)
        policy_review = self.policy.review_plan(plan, self.tools, merged_context)
        to_dict_safe = self._safe_to_dict

        return {
            "prompt": prompt,
            "context": merged_context,
            "intent_obj": intent,
            "intent": to_dict_safe(intent),
            "observation": preview["observation"],
            "analysis": analysis,
            "thought": preview["thought"],
            "specialist_obj": specialist,
            "specialist": to_dict_safe(specialist.profile) if hasattr(specialist, 'profile') else to_dict_safe(specialist),
            "agent_runtime": self.agents.runtime_status(specialist.profile.name) or {},
            "collaborators": [to_dict_safe(agent.profile) for agent in collaborators],
            "plan_obj": plan,
            "plan": to_dict_safe(plan),
            "policy": policy_review,
            "loop_trace": preview["loop_trace"],
        }

    def preview_prompt(self, prompt: str, context: dict[str, Any] | None = None, agent_name: str = "auto") -> dict[str, Any]:
        prepared = self._prepare(prompt, context=context, agent_name=agent_name)
        return {
            "intent": prepared["intent"],
            "observation": prepared["observation"],
            "analysis": prepared["analysis"],
            "thought": prepared["thought"],
            "specialist": prepared["specialist"],
            "agent_runtime": prepared["agent_runtime"],
            "collaborators": prepared["collaborators"],
            "plan": prepared["plan"],
            "policy": prepared["policy"],
            "loop_trace": prepared["loop_trace"],
        }

    def handle_prompt(self, prompt: str, context: dict[str, Any] | None = None, agent_name: str = "auto") -> dict[str, Any]:
        prepared = self._prepare(prompt, context=context, agent_name=agent_name)
        runtime_name = prepared["agent_runtime"].get("name", prepared["specialist"]["name"])
        sync_job_id = f"sync_{prepared['specialist']['name']}_{prepared['plan']['plan_id']}"
        track_queue = not bool(prepared["context"].get("_skip_agent_queue", False))
        if track_queue:
            self.agent_runtime.start(runtime_name, sync_job_id)
        loop_result = self.loop.run(
            prompt=prompt,
            context=prepared["context"],
            specialist=prepared["specialist_obj"],
            intent=prepared["intent_obj"],
            initial_analysis=prepared["analysis"],
            initial_observation=prepared["observation"],
            initial_thought=prepared["thought"],
        )
        execution = loop_result["execution_obj"]
        reflection = loop_result["reflection_obj"]
        improvement = self.self_improve.observe(
            {
                "prompt": prompt,
                "intent": prepared["intent"],
                "analysis": prepared["analysis"],
                "plan": loop_result["plan"],
                "execution": loop_result["execution"],
                "reflection": loop_result["reflection"],
            }
        )
        final_text = self.reasoning.summarize(prompt, execution.summary, context=prepared["context"])
        # Handle both old intent object format and new dict format
        intent_name = prepared["intent"].get("type", "auto") if isinstance(prepared["intent"], dict) else prepared["intent"].get("name", "auto")
        conversation_meta = {
            "intent": intent_name,
            "agent": prepared["specialist"]["name"],
            "agent_scope": prepared["context"].get("agent_memory_scope", ""),
        }
        self.memory.remember_conversation("user", prompt, conversation_meta)
        self.memory.remember_conversation("assistant", final_text, conversation_meta)
        if track_queue:
            self.agent_runtime.complete(runtime_name, sync_job_id, success=execution.success)
        return {
            "intent": prepared["intent"],
            "observation": prepared["observation"],
            "analysis": prepared["analysis"],
            "thought": prepared["thought"],
            "specialist": prepared["specialist"],
            "agent_runtime": self.agent_runtime.get(runtime_name) or prepared["agent_runtime"],
            "collaborators": prepared["collaborators"],
            "plan": loop_result["plan"],
            "policy": prepared["policy"],
            "execution": loop_result["execution"],
            "reflection": loop_result["reflection"],
            "loop_trace": loop_result["loop_trace"],
            "self_improvement": improvement,
            "reply": final_text,
            "tools": self.tools.catalog(),
            "memory": self.memory.recent(),
        }

    def submit_prompt(self, prompt: str, context: dict[str, Any] | None = None, agent_name: str = "auto") -> dict[str, Any]:
        preview = self.preview_prompt(prompt, context=context, agent_name=agent_name)
        runtime_name = preview.get("agent_runtime", {}).get("name", preview["specialist"]["name"])

        def _runner(job, control) -> dict[str, Any]:
            self.agent_runtime.start(runtime_name, job.job_id)
            runner_context = {**job.context, "_skip_agent_queue": True}
            result: dict[str, Any] | None = None
            success = False
            try:
                result = self._run_background_plan(job, runner_context, control)
                success = bool(result.get("execution", {}).get("success", False))
                return result
            finally:
                self.agent_runtime.complete(runtime_name, job.job_id, success=success)

        job = self.jobs.submit(
            prompt=prompt,
            agent_name=agent_name,
            runner=_runner,
            context=context,
            plan=preview.get("plan", {}),
            preview=preview,
        )
        self.agent_runtime.enqueue(runtime_name, job.job_id)
        return {
            "job": self._safe_to_dict(job),
            "preview": preview,
        }

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job:
            return {"error": "job not found", "job_id": job_id}
        return job.to_dict()

    def list_jobs(self) -> dict[str, Any]:
        jobs = [job.to_dict() for job in self.jobs.list()]
        return {"jobs": jobs, "counts": self.jobs.counts()}

    def pause_job(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.pause(job_id)
        if not job:
            return {"error": "job not found", "job_id": job_id}
        return job.to_dict()

    def resume_job(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job:
            return {"error": "job not found", "job_id": job_id}
        preview = dict(job.preview or {})
        runtime_name = preview.get("agent_runtime", {}).get("name", job.agent_name)

        def _runner(record, control) -> dict[str, Any]:
            self.agent_runtime.start(runtime_name, record.job_id)
            runner_context = {**record.context, "_skip_agent_queue": True}
            result: dict[str, Any] | None = None
            success = False
            try:
                result = self._run_background_plan(record, runner_context, control)
                success = bool(result.get("execution", {}).get("success", False))
                return result
            finally:
                self.agent_runtime.complete(runtime_name, record.job_id, success=success)

        resumed = self.jobs.resume(job_id, _runner)
        if resumed is None:
            return {"error": "job not found", "job_id": job_id}
        return resumed.to_dict()

    def wait_for_idle(self, timeout_s: float = 5.0) -> dict[str, Any]:
        self.jobs.wait_all(timeout_s=timeout_s)
        return self.list_jobs()

    def list_schedules(self) -> dict[str, Any]:
        items = self.scheduler.list()
        return {"schedules": items, "count": len(items)}

    def run_due_schedules(self) -> dict[str, Any]:
        result = self.scheduler.run_due()
        self.telemetry.record("scheduler.run_due", result)
        return result

    def daemon_status(self) -> dict[str, Any]:
        return self.daemon.status()

    def daemon_start(self) -> dict[str, Any]:
        result = self.daemon.start()
        self.telemetry.record("daemon.start", result)
        return result

    def daemon_stop(self) -> dict[str, Any]:
        result = self.daemon.stop()
        self.telemetry.record("daemon.stop", result)
        return result

    def daemon_tick(self) -> dict[str, Any]:
        result = self.daemon.tick()
        self.telemetry.record("daemon.tick", result)
        return result

    def list_skills(self) -> dict[str, Any]:
        skills = [skill.to_dict() for skill in self.skills.list()]
        return {"skills": skills, "count": len(skills)}

    def get_skill(self, name: str) -> dict[str, Any]:
        skill = self.skills.get(name)
        if not skill:
            return {"error": "skill not found", "name": name}
        return skill.to_dict()

    def run_skill(self, name: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        skill = self.skills.get(name)
        if not skill:
            return {"error": "skill not found", "name": name}
        self.skills.record_use(name)
        from ..contracts import Plan, PlanStep

        plan = Plan(
            goal=skill.source_prompt,
            intent=skill.intent,
            strategy="manual_skill_run",
            notes=[f"Executed learned skill `{name}` by explicit request."],
            steps=[
                PlanStep(
                    tool=step["tool"],
                    action=step["action"],
                    arguments=dict(step.get("arguments", {})),
                    reason=f"Explicit skill run for `{name}`.",
                )
                for step in skill.steps
            ],
        )
        execution = self.executor.execute(plan, context=context)
        reflection = self.reflection.reflect(plan, execution)
        return {
            "skill": skill.to_dict(),
            "plan": plan.to_dict(),
            "execution": execution.to_dict(),
            "reflection": reflection.to_dict(),
        }

    def telemetry_summary(self) -> dict[str, Any]:
        return {"metrics": self.telemetry.metrics(), "events": self.telemetry.recent()}

    def config_summary(self) -> dict[str, Any]:
        return self.config.to_dict()

    def monitor_summary(self) -> dict[str, Any]:
        return self.monitor.snapshot()

    def compat_summary(self) -> dict[str, Any]:
        return self.compat.summary()

    def list_plugins(self) -> dict[str, Any]:
        plugins = self.plugins.list()
        return {"plugins": plugins, "count": len(plugins)}

    def get_plugin(self, name: str) -> dict[str, Any]:
        plugin = self.plugins.get(name)
        if plugin is None:
            return {"error": "plugin not found", "name": name}
        return plugin

    def run_plugin_workflow(self, plugin_name: str, workflow_name: str, input_text: str = "") -> dict[str, Any]:
        return self.plugins.run_workflow(plugin_name, workflow_name, self.tools, input_text=input_text)

    def list_agents(self) -> dict[str, Any]:
        agents = self.agent_runtime.list()
        return {"agents": agents, "count": len(agents)}

    def get_agent(self, name: str) -> dict[str, Any]:
        agent = self.agent_runtime.get(name)
        if agent is None:
            return {"error": "agent not found", "name": name}
        return agent

    def status(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self.config.workspace_root),
            "data_dir": str(self.config.data_dir),
            "models": self.models.status(),
            "job_counts": self.jobs.counts(),
            "schedule_count": len(self.scheduler.list()),
            "daemon": self.daemon.status(),
            "memory_items": len(self.memory.recent()),
            "tools": len(self.tools.catalog()),
            "skills": len(self.skills.list()),
            "plugins": len(self.plugins.list()),
            "agent_count": len(self.agent_runtime.list()),
            "compat": self.compat.summary(),
            "policy": self.policy.describe(),
            "telemetry": self.telemetry.metrics(),
            "agents": [agent.profile.to_dict() for agent in self.agents.collaborate("general", "auto")],
        }

    def _run_background_plan(self, job: Any, context: dict[str, Any], control: Any) -> dict[str, Any]:
        from ..contracts import Plan, PlanStep

        plan_data = dict(job.plan or {})
        steps = [
            PlanStep(
                tool=step.get("tool", ""),
                action=step.get("action", ""),
                arguments=dict(step.get("arguments", {})),
                reason=step.get("reason", ""),
                status=step.get("status", "pending"),
                step_id=step.get("step_id", ""),
            )
            for step in plan_data.get("steps", [])
        ]
        plan = Plan(
            goal=plan_data.get("goal", job.prompt),
            intent=plan_data.get("intent", "general"),
            strategy=plan_data.get("strategy", "background"),
            steps=steps,
            notes=list(plan_data.get("notes", [])),
            plan_id=plan_data.get("plan_id", ""),
            created_at=float(plan_data.get("created_at", 0.0) or 0.0),
        )
        checkpoint = dict(job.checkpoint or {})
        start_index = int(checkpoint.get("next_step_index", 0) or 0)
        existing_results = list(checkpoint.get("results", []))

        def _before_step(step, index, report, context_data) -> None:
            control.wait_if_paused()
            self.jobs.record_checkpoint(
                job.job_id,
                {
                    "plan_id": plan.plan_id,
                    "next_step_index": index,
                    "active_step_id": step.step_id,
                    "results": [item.to_dict() for item in report.results],
                },
            )

        def _after_step(step, index, result, report, context_data) -> None:
            self.jobs.record_checkpoint(
                job.job_id,
                {
                    "plan_id": plan.plan_id,
                    "next_step_index": index + 1,
                    "active_step_id": step.step_id,
                    "results": [item.to_dict() for item in report.results],
                },
            )

        execution = self.executor.execute(
            plan,
            context=context,
            start_index=start_index,
            existing_results=existing_results,
            before_step=_before_step,
            after_step=_after_step,
        )
        reflection = self.reflection.reflect(plan, execution)
        final_text = self.reasoning.summarize(job.prompt, execution.summary, context=context)
        self.memory.remember_conversation("user", job.prompt, {"intent": plan.intent, "agent": job.agent_name})
        self.memory.remember_conversation("assistant", final_text, {"intent": plan.intent, "agent": job.agent_name})
        self.jobs.record_checkpoint(
            job.job_id,
            {
                "plan_id": plan.plan_id,
                "next_step_index": len(plan.steps),
                "active_step_id": "",
                "results": [item.to_dict() for item in execution.results],
            },
        )
        return {
            "intent": job.preview.get("intent", {}),
            "analysis": job.preview.get("analysis", {}),
            "specialist": job.preview.get("specialist", {}),
            "plan": plan.to_dict(),
            "execution": execution.to_dict(),
            "reflection": reflection.to_dict(),
            "reply": final_text,
        }

    # === Extensions support ===
    def list_extensions(self):
        """List all extensions."""
        if not hasattr(self, '_extensions_manager'):
            return []
        return self._extensions_manager.list_extensions()

    def get_extension_info(self, name: str):
        """Get info about a specific extension."""
        if not hasattr(self, '_extensions_manager'):
            return {"error": "Extensions manager not initialized"}
        return self._extensions_manager.get_extension_info(name)

    def enable_extension(self, name: str):
        """Enable an extension."""
        if not hasattr(self, '_extensions_manager'):
            return {"ok": False, "error": "Extensions manager not initialized"}
        return self._extensions_manager.enable_extension(name)

    def disable_extension(self, name: str):
        """Disable an extension."""
        if not hasattr(self, '_extensions_manager'):
            return {"ok": False, "error": "Extensions manager not initialized"}
        return self._extensions_manager.disable_extension(name)

    def install_extension(self, path_or_url: str):
        """Install an extension."""
        if not hasattr(self, '_extensions_manager'):
            return {"ok": False, "error": "Extensions manager not initialized"}
        return self._extensions_manager.install_extension(path_or_url)

    def uninstall_extension(self, name: str):
        """Uninstall an extension."""
        if not hasattr(self, '_extensions_manager'):
            return {"ok": False, "error": "Extensions manager not initialized"}
        return self._extensions_manager.uninstall_extension(name)

    def list_extension_commands(self):
        """List all commands from extensions."""
        if not hasattr(self, '_extensions_manager'):
            return []
        return self._extensions_manager.list_extension_commands()

    # === Routes support ===
    def list_routes(self):
        """List all API routes."""
        routes = [
            {"method": "GET", "path": "/health", "description": "Health check"},
            {"method": "GET", "path": "/tools", "description": "Tool catalog"},
            {"method": "GET", "path": "/status", "description": "Runtime status"},
            {"method": "GET", "path": "/config", "description": "Configuration"},
            {"method": "GET", "path": "/agents", "description": "List agents"},
            {"method": "POST", "path": "/run", "description": "Execute prompt"},
            {"method": "POST", "path": "/preview", "description": "Preview prompt"},
            {"method": "GET", "path": "/extensions", "description": "List extensions"},
            {"method": "POST", "path": "/extensions/install", "description": "Install extension"},
            {"method": "GET", "path": "/routes", "description": "List routes"},
            {"method": "GET", "path": "/links", "description": "List links"},
            {"method": "POST", "path": "/links/add", "description": "Add link"},
        ]
        return routes

    def get_route_info(self, route: str):
        """Get info about a specific route."""
        routes = self.list_routes()
        for r in routes:
            if r["path"] == route:
                return r
        return {"error": f"Route '{route}' not found"}

    # === Links support ===
    def list_links(self):
        """List all resource links."""
        if not hasattr(self, '_links_manager'):
            return []
        return self._links_manager.list_links()

    def add_link(self, name: str, url: str):
        """Add a named resource link."""
        if not hasattr(self, '_links_manager'):
            return {"ok": False, "error": "Links manager not initialized"}
        return self._links_manager.add_link(name, url)

    def remove_link(self, name: str):
        """Remove a resource link."""
        if not hasattr(self, '_links_manager'):
            return {"ok": False, "error": "Links manager not initialized"}
        return self._links_manager.remove_link(name)

    def open_link(self, name: str):
        """Open a resource link."""
        if not hasattr(self, '_links_manager'):
            return {"ok": False, "error": "Links manager not initialized"}
        return self._links_manager.open_link(name)

    # === Serving support ===
    def serve_api(self, host: str = "127.0.0.1", port: int = 8011, detached: bool = False):
        """Start the API server."""
        import subprocess
        import sys
        if detached:
            script_path = "C:/Users/peter/Desktop/jarvis/jarvis_os/interface/api_server.py"
            pid = subprocess.Popen(
                [sys.executable, script_path, "--host", host, "--port", str(port), "--detached"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            ).pid
            return {"ok": True, "pid": pid, "host": host, "port": port, "detached": True}
        else:
            from ..interface.api_server import _start_server
            _start_server(host, port)
            return {"ok": True}

    def stop_api_server(self):
        """Stop the API server."""
        return {"ok": False, "error": "Not implemented - use /daemon/stop instead"}

    def api_server_status(self):
        """Get API server status."""
        return {"status": "unknown", "message": "API server status check not implemented"}

    # Add properties for managers
    @property
    def extensions(self):
        return self._extensions_manager if hasattr(self, '_extensions_manager') else None

    @property
    def links(self):
        return self._links_manager if hasattr(self, '_links_manager') else None

