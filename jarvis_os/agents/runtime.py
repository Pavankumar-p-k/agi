from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..contracts import AgentProfile, AgentRuntimeRecord


def _runtime_name(agent_name: str) -> str:
    return agent_name.replace("_agent", "")


class AgentRuntimeManager:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.root = Path(config.data_dir) / "agents"
        self.root.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, AgentRuntimeRecord] = {}

    def register(self, profile: AgentProfile, *, model_task: str = "reasoning") -> AgentRuntimeRecord:
        runtime_name = _runtime_name(profile.name)
        workspace_root = self.root / runtime_name / "workspace"
        workspace_root.mkdir(parents=True, exist_ok=True)
        record = self._records.get(runtime_name)
        if record is None:
            record = AgentRuntimeRecord(
                name=runtime_name,
                focus=profile.focus,
                strengths=list(profile.strengths),
                workspace_root=str(workspace_root),
                memory_scope=runtime_name,
                model_task=model_task,
                queue={"queued": 0, "running": 0, "completed": 0, "failed": 0},
            )
            self._records[runtime_name] = record
        else:
            record.focus = profile.focus
            record.strengths = list(profile.strengths)
            record.model_task = model_task
        self._persist(record)
        return record

    def list(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in sorted(self._records.values(), key=lambda item: item.name)]

    def get(self, name: str) -> dict[str, Any] | None:
        runtime_name = _runtime_name(name)
        record = self._records.get(runtime_name)
        if record is None:
            return None
        return record.to_dict()

    def context_for(self, name: str) -> dict[str, Any]:
        runtime_name = _runtime_name(name)
        record = self._records[runtime_name]
        return {
            "agent_name": record.name,
            "agent_workspace": record.workspace_root,
            "workspace_root": record.workspace_root,
            "agent_memory_scope": record.memory_scope,
            "agent_model_task": record.model_task,
        }

    def enqueue(self, name: str, job_id: str) -> None:
        record = self._records[_runtime_name(name)]
        record.queue["queued"] = record.queue.get("queued", 0) + 1
        self._persist(record)

    def start(self, name: str, job_id: str) -> None:
        record = self._records[_runtime_name(name)]
        if record.queue.get("queued", 0) > 0:
            record.queue["queued"] -= 1
        record.queue["running"] = record.queue.get("running", 0) + 1
        record.active_job_id = job_id
        self._persist(record)

    def complete(self, name: str, job_id: str, *, success: bool) -> None:
        record = self._records[_runtime_name(name)]
        if record.queue.get("running", 0) > 0:
            record.queue["running"] -= 1
        key = "completed" if success else "failed"
        record.queue[key] = record.queue.get(key, 0) + 1
        if record.active_job_id == job_id:
            record.active_job_id = ""
        self._persist(record)

    def _persist(self, record: AgentRuntimeRecord) -> None:
        target = Path(record.workspace_root).parent / "state.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
