"""brain.prompt_optimizer — prompts refinement from agent output cycles.

Phase contract (``tests/unit/test_docker_readiness.py``): when the agent
output mapping is empty or disabled (``AGENT_OUTPUT_TYPE is None``),
``run_cycle()`` must return ``[]`` without side effects.
"""
from __future__ import annotations

from typing import Any, Optional

__all__ = ["PromptOptimizer"]


class PromptOptimizer:
    """Turns recorded agent outputs into prompt-improvement suggestions.

    ``AGENT_OUTPUT_TYPE`` selects the feedback source (a mapping of agent
    invocation records). ``None`` disables the cycle entirely — the honest
    result is an empty suggestion list, never a crash.
    """

    AGENT_OUTPUT_TYPE: Optional[Any] = None

    def __init__(self, output_type: Optional[Any] = None) -> None:
        if output_type is not None:
            self.AGENT_OUTPUT_TYPE = output_type

    async def run_cycle(self) -> list[dict[str, Any]]:
        """One optimization pass; [] when disabled or nothing to learn from."""
        outputs = self.AGENT_OUTPUT_TYPE
        if outputs is None:
            return []
        items: list[Any] = []
        if isinstance(outputs, dict):
            items = list(outputs.values())
        elif isinstance(outputs, (list, tuple)):
            items = list(outputs)
        else:
            return []
        suggestions: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict) and item.get("prompt_hint"):
                suggestions.append({
                    "prompt": item.get("prompt_hint"),
                    "reason": item.get("reason", "agent-output"),
                })
        return suggestions
