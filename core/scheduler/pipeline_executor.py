"""PipelineExecutor — the only adapter between Scheduler and the canonical pipeline.

Scheduler never imports pipeline internals except this module.
"""
from __future__ import annotations

import logging
from typing import Any

from core.pipeline.messages import Request
from core.pipeline.pipeline import process_message

logger = logging.getLogger(__name__)


async def pipeline_executor(
    activity_id: str,
    goal: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a scheduled activity through the canonical ``process_message()``.

    This is an ``ExecutorFn``-compatible callable that can be registered in
    ``SchedulerRegistry``.  It creates a ``Request`` from the scheduled
    activity's goal and delegates to ``process_message()``.

    Args:
        activity_id: The scheduled activity's ID (passed to metadata for
            traceability).
        goal: The user-facing goal string, used as the pipeline's raw input.
        metadata: Optional metadata forwarded to the request.

    Returns:
        A dict with the outcome, including ``text``, ``error``, ``data``, and
        ``metadata`` (token counts, activity_id, trace_id, etc.).
    """
    meta = dict(metadata or {})
    meta["scheduler_activity_id"] = activity_id

    request = Request(
        text=goal,
        transport="scheduler",
        metadata=meta,
    )

    logger.info(
        "PipelineExecutor: executing activity %s via canonical pipeline",
        activity_id,
    )

    try:
        response = await process_message(request)

        result: dict[str, Any] = {
            "activity_id": activity_id,
            "text": response.text,
            "error": response.error,
            "data": response.data,
            "metadata": response.metadata,
            "success": response.error is None,
        }
        return result
    except Exception as exc:
        logger.exception(
            "PipelineExecutor: activity %s failed: %s", activity_id, exc,
        )
        return {
            "activity_id": activity_id,
            "text": "",
            "error": str(exc),
            "data": None,
            "metadata": {},
            "success": False,
        }
