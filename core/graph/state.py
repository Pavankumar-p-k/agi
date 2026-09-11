from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentPhase(str, Enum):
    THINKING = "thinking"
    TOOL_CALLING = "tool_calling"
    PAUSED = "paused"
    FINISHED = "finished"
    VERIFYING = "verifying"
    ERROR = "error"


@dataclass
class RoundState:
    round_num: int = 0
    response: str = ""
    tool_blocks: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_num": self.round_num,
            "response": self.response,
            "tool_blocks": [getattr(tb, "to_dict", lambda: {"tool": getattr(tb, "tool", None), "input": getattr(tb, "input", None)})() for tb in self.tool_blocks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RoundState":
        if not data:
            return cls()
        tool_blocks = data.get("tool_blocks") or []
        converted = []
        for tb in tool_blocks:
            if hasattr(tb, "tool"):
                converted.append(tb)
            elif isinstance(tb, dict):
                converted.append(type("ToolBlock", (), tb)())
        return cls(round_num=int(data.get("round_num", 0)), response=str(data.get("response", "")), tool_blocks=converted)


@dataclass
class AgentState:
    endpoint_url: str = ""
    model: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    phase: AgentPhase = AgentPhase.THINKING
    round_num: int = 0
    round_state: RoundState | None = None
    structured_reasoning: list[dict[str, Any]] = field(default_factory=list)
    parallel_sub_agents: list[dict[str, Any]] = field(default_factory=list)
    parallel_results: list[dict[str, Any]] = field(default_factory=list)
    pause_before_effectful: bool = False
    paused_tool_data: list[dict[str, Any]] | None = None
    resume_action: str = ""
    resume_feedback: str = ""
    events: list[str] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    mcp_mgr: Any = None
    headers: Any = None

    def __post_init__(self) -> None:
        if self.round_state is None:
            self.round_state = RoundState()

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint_url": self.endpoint_url,
            "model": self.model,
            "messages": self.messages,
            "phase": self.phase.value if isinstance(self.phase, AgentPhase) else str(self.phase),
            "round_state": self.round_state.to_dict() if self.round_state else None,
            "structured_reasoning": self.structured_reasoning,
            "parallel_sub_agents": self.parallel_sub_agents,
            "parallel_results": self.parallel_results,
            "pause_before_effectful": self.pause_before_effectful,
            "paused_tool_data": self.paused_tool_data,
            "resume_action": self.resume_action,
            "resume_feedback": self.resume_feedback,
            "events": [],
            "run_id": self.run_id,
            "mcp_mgr": None,
            "headers": None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AgentState":
        if not data:
            data = {}
        phase_name = data.get("phase")
        if isinstance(phase_name, AgentPhase):
            phase = phase_name
        elif isinstance(phase_name, str):
            try:
                phase = AgentPhase(phase_name)
            except ValueError:
                phase = AgentPhase.THINKING
        else:
            phase = AgentPhase.THINKING
        state = cls(
            endpoint_url=str(data.get("endpoint_url", "")),
            model=str(data.get("model", "")),
            messages=list(data.get("messages") or []),
            phase=phase,
            round_num=int(data.get("round_num", 0) or 0),
            round_state=RoundState.from_dict(data.get("round_state")),
            structured_reasoning=list(data.get("structured_reasoning") or []),
            parallel_sub_agents=list(data.get("parallel_sub_agents") or []),
            parallel_results=list(data.get("parallel_results") or []),
            pause_before_effectful=bool(data.get("pause_before_effectful", False)),
            paused_tool_data=data.get("paused_tool_data"),
            resume_action=str(data.get("resume_action", "")),
            resume_feedback=str(data.get("resume_feedback", "")),
            events=[],
            run_id=str(data.get("run_id") or uuid.uuid4().hex[:12]),
        )
        return state


THINK_RE = re.compile(r"(think.*?)(?:</think>|$)", re.IGNORECASE | re.DOTALL)
