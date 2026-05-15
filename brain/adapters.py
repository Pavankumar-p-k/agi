from __future__ import annotations

from typing import Any, Optional


class _NullStack:
    async def evaluate(self, context: Any) -> dict[str, Any]:
        return {"allowed": True, "delegate_to": "JarvisBrain", "reason": "Null adapter"}


class BrainAdapter:
    """
    Bridges external callers to the canonical brain execution interface.
    """

    def __init__(self, authority_stack: Any = None) -> None:
        self.authority_stack = authority_stack or _NullStack()

    async def evaluate(self, context: Any) -> dict[str, Any]:
        return await self.authority_stack.evaluate(context)

    async def think(self, context: Any) -> Any:
        return type('BrainResult', (), {'reply': '[BrainAdapter stub] No-op.'})()

    async def execute_goal(self, goal: str, context: Any = None) -> dict[str, Any]:
        return {"success": True, "result": f"Executed goal: {goal}", "delegate": self.__class__.__name__}

    def status(self) -> dict[str, Any]:
        return {"name": self.__class__.__name__, "status": "stub"}


class JarvisBrainAdapter(BrainAdapter):
    """Conversational brain adapter."""
    pass


class AIOrchestratorAdapter(BrainAdapter):
    """Autonomous orchestrator adapter."""
    pass


class HybridOrchestratorAdapter(BrainAdapter):
    """Hybrid local/cloud orchestrator adapter."""
    pass


class CognitiveAgentAdapter(BrainAdapter):
    """Self-improvement agent adapter."""
    pass
