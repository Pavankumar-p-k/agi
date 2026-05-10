from __future__ import annotations

from typing import Any


class RuntimeMonitor:
    def __init__(self, *, config: Any, jobs: Any, agent_runtime: Any, scheduler: Any, daemon: Any, telemetry: Any, models: Any) -> None:
        self.config = config
        self.jobs = jobs
        self.agent_runtime = agent_runtime
        self.scheduler = scheduler
        self.daemon = daemon
        self.telemetry = telemetry
        self.models = models

    def snapshot(self) -> dict[str, Any]:
        jobs = self.jobs.list()
        agents = self.agent_runtime.list()
        model_status = self.models.status()
        daemon_status = self.daemon.status()
        active_agents = [agent["name"] for agent in agents if agent.get("queue", {}).get("running", 0) > 0]
        busy_agents = [
            {
                "name": agent["name"],
                "running": agent.get("queue", {}).get("running", 0),
                "queued": agent.get("queue", {}).get("queued", 0),
                "active_job_id": agent.get("active_job_id", ""),
            }
            for agent in agents
            if agent.get("queue", {}).get("running", 0) or agent.get("queue", {}).get("queued", 0)
        ]
        return {
            "workspace_root": str(self.config.workspace_root),
            "data_dir": str(self.config.data_dir),
            "active_agents": active_agents,
            "busy_agents": busy_agents,
            "job_counts": self.jobs.counts(),
            "queued_jobs": [job.to_dict() for job in jobs if job.status in {"queued", "running"}][:10],
            "paused_jobs": [job.to_dict() for job in jobs if job.status == "paused"][:10],
            "failed_jobs": [job.to_dict() for job in jobs if job.status == "failed"][:10],
            "schedule_count": len(self.scheduler.list()),
            "due_schedule_count": len(self.scheduler.due()),
            "daemon": daemon_status,
            "telemetry": self.telemetry.metrics(),
            "models": model_status,
            "health": {
                "jobs_stalled": bool(self.jobs.counts().get("running", 0) and not active_agents),
                "models_ready": bool(model_status.get("ready", False)),
                "daemon_running": bool(daemon_status.get("running", False)),
            },
        }
