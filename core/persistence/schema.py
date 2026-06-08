from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class AgentCheckpoint:
    """Serializable snapshot of agent execution state.

    Captures the full state needed to resume an agent mid-execution:
    plan structure, progress, tool results, variables, and context.
    """

    session_key: str
    agent_id: str = ""
    task: str = ""
    plan: list[dict[str, Any]] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)
    pending_tasks: list[str] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    memory_snapshot: list[dict[str, Any]] = field(default_factory=list)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    MAX_TOOL_RESULTS = 100

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def add_tool_result(self, result: dict[str, Any]) -> None:
        self.tool_results.append(result)
        if len(self.tool_results) > self.MAX_TOOL_RESULTS:
            self.tool_results = self.tool_results[-self.MAX_TOOL_RESULTS:]
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_completed(self, task_id: str) -> None:
        if task_id in self.pending_tasks:
            self.pending_tasks.remove(task_id)
        if task_id not in self.completed_tasks:
            self.completed_tasks.append(task_id)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_failed(self, task_id: str) -> None:
        if task_id in self.pending_tasks:
            self.pending_tasks.remove(task_id)
        if task_id not in self.failed_tasks:
            self.failed_tasks.append(task_id)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_key": self.session_key,
            "agent_id": self.agent_id,
            "task": self.task,
            "plan": self.plan,
            "completed_tasks": self.completed_tasks,
            "pending_tasks": self.pending_tasks,
            "failed_tasks": self.failed_tasks,
            "tool_results": self.tool_results[-50:],
            "variables": self.variables,
            "memory_snapshot": self.memory_snapshot[-20:],
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentCheckpoint:
        return cls(
            session_key=data.get("session_key", ""),
            agent_id=data.get("agent_id", ""),
            task=data.get("task", ""),
            plan=data.get("plan", []),
            completed_tasks=data.get("completed_tasks", []),
            pending_tasks=data.get("pending_tasks", []),
            failed_tasks=data.get("failed_tasks", []),
            tool_results=data.get("tool_results", []),
            variables=data.get("variables", {}),
            memory_snapshot=data.get("memory_snapshot", []),
            version=data.get("version", 1),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
