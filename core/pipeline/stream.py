"""Pipeline streaming event contract.

``Pipeline.stream(ctx)`` emits these events; ``stream_pipeline(request)`` is
the request-level entry point used by streaming transports. Terminal events
are exactly one of ``pipeline_end``, ``pipeline_error``, ``pipeline_cancelled``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from core.pipeline.messages import Request

PIPELINE_START = "pipeline_start"
PIPELINE_END = "pipeline_end"
PIPELINE_ERROR = "pipeline_error"
PIPELINE_CANCELLED = "pipeline_cancelled"
STAGE_START = "stage_start"
STAGE_END = "stage_end"
STAGE_ERROR = "stage_error"


@dataclass(frozen=True)
class StreamEvent:
    """One pipeline progress event."""

    event_type: str
    stage: str | None = None
    data: dict | None = None
    error: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.event_type in (PIPELINE_END, PIPELINE_ERROR, PIPELINE_CANCELLED)


class StreamEventType:
    """Enum-style namespace of the event names (string values)."""

    PIPELINE_START = PIPELINE_START
    PIPELINE_END = PIPELINE_END
    PIPELINE_ERROR = PIPELINE_ERROR
    PIPELINE_CANCELLED = PIPELINE_CANCELLED
    STAGE_START = STAGE_START
    STAGE_END = STAGE_END
    STAGE_ERROR = STAGE_ERROR


async def stream_pipeline(request: Request) -> AsyncIterator[StreamEvent]:
    """Stream a request through the default pipeline."""
    from core.pipeline.pipeline import build_context, get_pipeline

    context = build_context(request)
    async for event in get_pipeline().stream(context):
        yield event


__all__ = [
    "StreamEvent",
    "StreamEventType",
    "stream_pipeline",
    "PIPELINE_START",
    "PIPELINE_END",
    "PIPELINE_ERROR",
    "PIPELINE_CANCELLED",
    "STAGE_START",
    "STAGE_END",
    "STAGE_ERROR",
]
