from __future__ import annotations

import time
from typing import Any

from ..contracts import Plan, PlanStep


class ReasoningEngine:
    """Legacy reasoning engine - now simplified for backward compatibility.
    New system uses Critic engine for evaluation instead."""
    def __init__(self, models: Any, registry: Any, memory: Any) -> None:
        self.models = models
        self.registry = registry
        self.memory = memory

    def observe(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Retrieve memory context for awareness."""
        ctx = context or {}
        memory_scope = str(ctx.get("agent_memory_scope", "")).strip()
        metadata_filter = {"agent_scope": memory_scope} if memory_scope else None
        retrieved = self.memory.build_context(prompt, metadata_filter=metadata_filter)
        return {
            "timestamp": time.time(),
            "memory_hits": self.memory.recall(prompt, top_k=3, metadata_filter=metadata_filter),
            "recent_memory": self.memory.recent(limit=3),
            "recent_conversation": retrieved.get("recent_conversation", []),
            "knowledge_hits": retrieved.get("knowledge_hits", []),
            "event_hits": retrieved.get("event_hits", []),
            "feedback": dict(ctx.get("feedback", {})),
        }

    def summarize(self, prompt: str, execution_summary: str, context: dict[str, Any] | None = None) -> str:
        """Summarize execution output using LLM."""
        ctx = context or {}
        if ctx.get("_skip_agent_queue"):
            return execution_summary
        task = str(ctx.get("agent_model_task", "reasoning")) or "reasoning"
        response = self.models.generate(
            prompt=f"Prompt: {prompt}\nExecution summary: {execution_summary}\nWrite a concise answer.",
            task=task,
            system="You are JARVIS. Summarize execution output clearly and briefly.",
            options={"timeout_s": 3},
        )
        if response.get("ok") and response.get("response"):
            return response["response"].strip()
        return execution_summary
