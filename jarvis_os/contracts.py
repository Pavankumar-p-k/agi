from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass(slots=True)
class Intent:
    name: str
    confidence: float
    actions: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    entities: dict[str, Any] = field(default_factory=dict)
    raw_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    arguments: list[str] = field(default_factory=list)
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    category: str = "general"
    permission: str = "safe"
    read_only: bool = False
    keywords: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlanStep:
    tool: str
    action: str
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    status: str = "pending"
    step_id: str = field(default_factory=lambda: _id("step"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Plan:
    goal: str
    intent: str
    strategy: str
    steps: list[PlanStep] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    plan_id: str = field(default_factory=lambda: _id("plan"))
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "intent": self.intent,
            "strategy": self.strategy,
            "notes": list(self.notes),
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(slots=True)
class ToolResult:
    tool: str
    success: bool
    output: Any = None
    error: str = ""
    duration_ms: int = 0
    step_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionReport:
    goal: str
    plan_id: str
    success: bool
    status: str = "completed"
    results: list[ToolResult] = field(default_factory=list)
    summary: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: float = field(default_factory=time.time)
    execution_id: str = field(default_factory=lambda: _id("exec"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "plan_id": self.plan_id,
            "success": self.success,
            "status": self.status,
            "summary": self.summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "execution_id": self.execution_id,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(slots=True)
class Reflection:
    status: str
    lessons: list[str] = field(default_factory=list)
    follow_up_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LoopStage:
    name: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LoopCycle:
    cycle_index: int
    stages: list[LoopStage] = field(default_factory=list)
    status: str = "pending"
    plan_id: str = ""
    execution_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_index": self.cycle_index,
            "status": self.status,
            "plan_id": self.plan_id,
            "execution_id": self.execution_id,
            "stages": [stage.to_dict() for stage in self.stages],
        }


@dataclass(slots=True)
class LoopTrace:
    goal: str
    intent: str
    status: str = "running"
    cycles: list[LoopCycle] = field(default_factory=list)
    loop_id: str = field(default_factory=lambda: _id("loop"))
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "intent": self.intent,
            "status": self.status,
            "loop_id": self.loop_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "cycles": [cycle.to_dict() for cycle in self.cycles],
        }


@dataclass(slots=True)
class AgentProfile:
    name: str
    focus: str
    strengths: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class JobRecord:
    job_id: str
    prompt: str
    status: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    agent_name: str = "auto"
    context: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)
    preview: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SkillRecord:
    name: str
    intent: str
    description: str
    source_prompt: str
    trigger_phrases: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    use_count: int = 0
    success_count: int = 0
    promoted_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PluginWorkflowRecord:
    name: str
    description: str
    steps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PluginManifestRecord:
    name: str
    version: str
    description: str
    path: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    workflows: list[PluginWorkflowRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "path": self.path,
            "tools": list(self.tools),
            "workflows": [workflow.to_dict() for workflow in self.workflows],
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AgentRuntimeRecord:
    name: str
    focus: str
    strengths: list[str]
    workspace_root: str
    memory_scope: str
    model_task: str
    queue: dict[str, int] = field(default_factory=dict)
    active_job_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
