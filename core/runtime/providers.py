"""ExecutionRuntime + RuntimeServices — executes plans against runtime services."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RuntimeServices:
    memory: Any = None
    observation: Any = None
    scheduler: Any = None
    metrics: Any = None
    event_bus: Any = None
    activity: Any = None


class ExecutionRuntime:
    """Runs a plan inside the runtime, publishing observations + metrics."""

    def __init__(self, services: Optional[RuntimeServices] = None) -> None:
        self.services = services or RuntimeServices()

    async def execute(self, ctx: Any, plan: Optional[dict] = None,
                      **kwargs: Any) -> dict:
        steps = (plan or {}).get("steps", []) or []
        texts: list[str] = []
        for step in steps:
            objective = str((step or {}).get("objective", ""))
            intent = str((step or {}).get("intent", "respond"))
            texts.append(f"executed {intent}: {objective}" if objective
                         else f"executed {intent}")

        output = {"text": "\n".join(texts) if texts else "", "steps": len(steps)}

        observation = self.services.observation if self.services else None
        if observation is not None:
            await observation.publish(ctx, {
                "type": "execution_result", "text": output["text"],
            })
        metrics = self.services.metrics if self.services else None
        if metrics is not None:
            metrics.record(ctx, {"steps": len(steps), "state": "completed"})
        return output


__all__ = ["ExecutionRuntime", "RuntimeServices"]
