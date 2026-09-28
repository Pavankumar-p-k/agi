"""ForgeAdapter — codegen specialist (smolagents CodeAgent on Ollama/cloud).

Forge writes code. It uses smolagents' CodeAgent when available (giving the
model a scratchpad to plan and execute code), falling back to plain LLM
code generation via core.llm_router.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from core.agents._sub_agent_base import AgentResult, SubAgent

try:
    from smolagents import CodeAgent, LiteLLMModel
except ImportError:  # smolagents optional — llm_router fallback used
    CodeAgent = None
    LiteLLMModel = None

ADAPTER_TIMEOUT = 300


class ForgeAgent(SubAgent):
    """Code generation & repair specialist."""

    NAME = "FORGE"
    DEFAULT_MODE = "generate"
    MODES = {
        "generate": "You are FORGE, an expert code generator. Output ONLY complete, runnable code with brief comments.",
        "repair": "You are FORGE in repair mode. Fix the given code and output ONLY the corrected code.",
        "refactor": "You are FORGE in refactor mode. Improve structure without changing behavior. Output ONLY refactored code.",
        "explain": "You are FORGE explaining code. Give a concise line-by-line explanation.",
    }

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._code_agent: Any = None

    def _get_smol_agent(self) -> Any:
        """Lazily build a smolagents CodeAgent pointed at the local model."""
        if self._code_agent is not None:
            return self._code_agent
        try:
            if CodeAgent is None:
                self._code_agent = False
                return False

            import os
            model_ref = os.getenv("CODE_MODEL", "ollama/qwen2.5-coder:3b")
            _, _, model_id = model_ref.partition("/")
            model = LiteLLMModel(
                model_id=f"ollama_chat/{model_id}",
                api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            )
            self._code_agent = CodeAgent(model=model, tools=[], add_base_tools=False)
            return self._code_agent
        except Exception:  # noqa: BLE001 — smolagents/model unavailable
            self._code_agent = False
            return False

    async def run(self, task: str, mode: str = "", lang: str = "Python", **kwargs: Any) -> AgentResult:
        start = time.monotonic()
        result = await super().run(task, mode=mode, **kwargs)
        if not result.success:
            return result

        # Try smolagents execution for real code runs (generate mode only).
        if (mode or self.DEFAULT_MODE) == "generate":
            smol = self._get_smol_agent()
            if smol:
                try:
                    output = await __import__("asyncio").to_thread(smol.run, task)
                    return AgentResult(
                        success=True,
                        output=str(output),
                        agent_name=self.NAME,
                        mode=mode or self.DEFAULT_MODE,
                        duration_s=time.monotonic() - start,
                        tokens_used=max(1, len(str(output)) // 4),
                        metadata={"engine": "smolagents"},
                    )
                except Exception as exc:  # noqa: BLE001
                    # Fall through to plain LLM output with the error noted.
                    result.metadata = {"engine": "llm", "smolagents_error": str(exc)}
                    return result
            result.metadata = {"engine": "llm"}
        return result


class ForgeAdapter:
    """Adapter bridge: agent_id/priority/execute() contract for the router."""

    agent_id = "forge"
    priority = 50
    keywords = ["codegen", "generate code", "write function", "implement function",
                "code for", "refactor code", "write class"]

    def __init__(self, **kwargs: Any):
        self._agent = ForgeAgent(**kwargs)

    @property
    def agent(self) -> ForgeAgent:
        return self._agent

    def can_handle(self, goal: str) -> bool:
        text = (goal or "").lower()
        return any(kw.lower() in text for kw in self.keywords)

    def info(self) -> dict[str, Any]:
        return {**self._agent.info(), "agent_id": self.agent_id, "priority": self.priority}

    async def run(self, task: str, mode: str = "", **kwargs: Any) -> Any:
        return await self._agent.run(task, mode=mode, **kwargs)

    async def execute(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> Any:
        from core.agents.base import AgentResult as _ToolResult
        result = await self._agent.run(goal, mode="generate", **kwargs)
        return _ToolResult(
            success=result.success,
            output=result.output,
            agent_id=self.agent_id,
            error=result.error,
            duration=result.duration_s,
            metadata={"mode": result.mode},
        )
