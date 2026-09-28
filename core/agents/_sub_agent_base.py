"""SubAgent base — the 9 LLM specialist agents (NEXUS, FORGE, ORACLE, ...).

SubAgents are prompt-driven specialists: each has a name, a set of modes
with per-mode system prompts, and runs its task through core.llm_router
(Ollama by default, any configured cloud provider).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentResult:
    """Result of a SubAgent run."""
    success: bool = True
    output: str = ""
    agent_name: str = ""
    mode: str = ""
    duration_s: float = 0.0
    error: str = ""
    tokens_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "mode": self.mode,
            "success": self.success,
            "output": self.output,
            "duration_s": self.duration_s,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "metadata": dict(self.metadata),
        }


class SubAgent:
    """Base for named specialist agents.

    Subclasses define:
      NAME:    uppercase agent name (e.g. "NEXUS")
      MODES:   dict[str, str] mapping mode -> system prompt
      DEFAULT_MODE: fallback when an unknown mode is requested
    """

    NAME: str = "BASE"
    MODES: dict[str, str] = {}
    DEFAULT_MODE: str = ""

    def __init__(self, **kwargs: Any):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def info(self) -> dict[str, Any]:
        return {
            "name": self.NAME,
            "modes": list(self.MODES.keys()),
            "default_mode": self.DEFAULT_MODE or next(iter(self.MODES), ""),
        }

    async def run(self, task: str, mode: str = "", **kwargs: Any) -> AgentResult:
        start = time.monotonic()
        use_mode = mode if mode in self.MODES else (self.DEFAULT_MODE or next(iter(self.MODES), ""))
        system = self.MODES.get(use_mode, "You are a helpful AI assistant.")
        try:
            # LLM access goes through the Execution stage gateway (Rule 1).
            from core.pipeline.stages.execution import complete_async
            result = await complete_async(str(task), role="chat", system=system)
            if result.is_err():
                raise result.unwrap()
            output = result.unwrap()
            return AgentResult(
                success=True,
                output=output,
                agent_name=self.NAME,
                mode=use_mode,
                duration_s=time.monotonic() - start,
                tokens_used=max(1, len(output) // 4),
            )
        except Exception as exc:  # noqa: BLE001 — report as failed result
            return AgentResult(
                success=False,
                output="",
                agent_name=self.NAME,
                mode=use_mode,
                duration_s=time.monotonic() - start,
                error=f"{type(exc).__name__}: {exc}",
            )
