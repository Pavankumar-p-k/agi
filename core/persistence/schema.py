from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AgentCheckpoint:
    session_key: str = ""
    agent_id: str = ""
    task: str = ""
    plan: list[dict[str, Any]] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    pending_tasks: list[str] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1
    MAX_TOOL_RESULTS: int = 50

    def add_tool_result(self, result: dict[str, Any]) -> None:
        self.tool_results.append(dict(result))
        if len(self.tool_results) > self.MAX_TOOL_RESULTS:
            self.tool_results = self.tool_results[-self.MAX_TOOL_RESULTS:]
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_completed(self, task: str) -> None:
        self.completed_tasks.append(task)
        if task in self.pending_tasks:
            self.pending_tasks.remove(task)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_failed(self, task: str) -> None:
        self.failed_tasks.append(task)
        if task in self.pending_tasks:
            self.pending_tasks.remove(task)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_key": self.session_key,
            "agent_id": self.agent_id,
            "task": self.task,
            "plan": list(self.plan),
            "variables": dict(self.variables),
            "pending_tasks": list(self.pending_tasks),
            "completed_tasks": list(self.completed_tasks),
            "failed_tasks": list(self.failed_tasks),
            "tool_results": self.tool_results[-self.MAX_TOOL_RESULTS:],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AgentCheckpoint":
        data = data or {}
        cp = cls(
            session_key=str(data.get("session_key", "")),
            agent_id=str(data.get("agent_id", "")),
            task=str(data.get("task", "")),
            plan=list(data.get("plan") or []),
            variables=dict(data.get("variables") or {}),
            pending_tasks=list(data.get("pending_tasks") or []),
            completed_tasks=list(data.get("completed_tasks") or []),
            failed_tasks=list(data.get("failed_tasks") or []),
            tool_results=list(data.get("tool_results") or []),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
            version=int(data.get("version", 1)),
        )
        cp.MAX_TOOL_RESULTS = int(data.get("MAX_TOOL_RESULTS", cp.MAX_TOOL_RESULTS))
        return cp
