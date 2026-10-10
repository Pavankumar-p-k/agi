"""core.scheduler.executors — default activity executors (Rule 8 allowed file).

``default_executor`` runs the goal text through the pipeline via the
scheduler's single sanctioned bridge (``core.scheduler.pipeline_executor``)
so scheduled activities honor the canonical stages. Dedicated node-type
executors can be layered later; the default must exist so the scheduler
never imports a half-broken graph.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

__all__ = ["default_executor", "register_executor", "get_executor"]

_EXECUTORS: dict[str, Callable[..., Awaitable[dict]]] = {}


def register_executor(node_type: str, fn: Callable[..., Awaitable[dict]]) -> None:
    """Attach an executor for a scheduler node type (extension seam)."""
    _EXECUTORS[node_type] = fn


def get_executor(node_type: str) -> Callable[..., Awaitable[dict]]:
    """Executor for *node_type* or the default one."""
    return _EXECUTORS.get(node_type, default_executor)


async def default_executor(activity_id: str, goal: str,
                           metadata: Any = None, **kwargs: Any) -> dict:
    """Run a scheduled activity through the canonical pipeline."""
    from core.scheduler.pipeline_executor import pipeline_executor

    return await pipeline_executor(activity_id, goal, metadata=metadata, **kwargs)
