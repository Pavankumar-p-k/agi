"""PipelineExecutor — the scheduler's only bridge into the pipeline (Rule 8).

The scheduler never imports pipeline internals directly; it calls
``pipeline_executor()``, which turns a scheduled activity into a Request,
runs it through the canonical ``process_message()`` path, and flattens the
Response into the dict shape the scheduler stores.
"""
from __future__ import annotations

from typing import Any, Optional

from core.pipeline.messages import Request, Response
from core.pipeline.pipeline import process_message

__all__ = ["pipeline_executor", "async_pipeline_executor"]


def _result(activity_id: str, *, success: bool, text: str = "",
            error: Optional[str] = None, metadata: Optional[dict] = None) -> dict:
    return {
        "success": success,
        "activity_id": activity_id,
        "text": text,
        "error": error,
        "metadata": dict(metadata or {}),
    }


async def pipeline_executor(
    activity_id: str,
    goal: str,
    metadata: Optional[dict] = None,
    **kwargs: Any,
) -> dict:
    """Run ``goal`` through the pipeline on behalf of scheduled activity."""
    request = Request(
        text=goal,
        transport="scheduler",
        metadata={**(metadata or {}), "scheduler_activity_id": activity_id},
    )
    try:
        response: Response = await process_message(request)
    except Exception as exc:  # noqa: BLE001 — scheduler records, never raises
        return _result(activity_id, success=False, error=f"{type(exc).__name__}: {exc}")
    return _result(
        activity_id,
        success=True,
        text=getattr(response, "text", "") or "",
        metadata=getattr(response, "metadata", None),
    )


async def async_pipeline_executor(*args: Any, **kwargs: Any) -> dict:
    """Alias kept for existing scheduler call sites."""
    return await pipeline_executor(*args, **kwargs)
