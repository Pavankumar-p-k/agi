"""WebSocket adapter — converts WebSocket chat messages to canonical
``Request`` / ``Response`` and delegates to the pipeline via
:func:`stream_pipeline` for live stage lifecycle events.

Both ``/ws/chat_stream`` and ``/ws/agent_stream`` call this adapter
instead of duplicating intent classification, LLM calls, and provider
fallback.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

from core.pipeline import stream_pipeline
from core.pipeline.messages import Request, Response
from core.pipeline.stream import StreamEvent

logger = logging.getLogger(__name__)


async def ws_adapter(
    text: str,
    user_id: str,
    session_id: str,
    *,
    context: str | None = None,
    attachments: list[dict] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict | None:
    """Process a WebSocket chat message through the pipeline (non-streaming).

    Returns a dict with ``"response"`` (the response text), or ``None``
    if the pipeline returned an error.
    """
    request = Request(
        text=text,
        transport="websocket",
        user_id=user_id,
        session_id=session_id,
        attachments=attachments or [],
        metadata={
            "context": context or "",
            **(metadata or {}),
        },
    )

    response: Response = await _run_pipeline(request)

    if response.error:
        logger.warning("Pipeline returned error for WS request: %s", response.error)
        return {
            "response": response.text or f"Error: {response.error}",
            "error": response.error,
        }

    return {
        "response": response.text,
        "error": None,
        "metadata": dict(response.metadata),
    }


async def stream_via_pipeline(
    ws: WebSocket,
    text: str,
    user_id: str,
    session_id: str,
    *,
    context: str | None = None,
    metadata: dict[str, Any] | None = None,
    tier_value: str = "local",
    model_name: str = "pipeline",
    intent: str = "chat",
) -> None:
    """Process a WS message through the pipeline and stream events live.

    Sends ``stage_start`` / ``stage_end`` events as the pipeline progresses,
    then word-token ``stream_token`` messages from the final response.
    """
    request = Request(
        text=text,
        transport="websocket",
        user_id=user_id,
        session_id=session_id,
        metadata={
            "context": context or "",
            **(metadata or {}),
        },
    )

    response_text = ""
    async for event in stream_pipeline(request):
        if event.event_type == "stage_start":
            await ws.send_json({
                "type": "stage_start",
                "stage": event.stage,
            })
        elif event.event_type == "stage_end":
            await ws.send_json({
                "type": "stage_end",
                "stage": event.stage,
                "data": event.data,
            })
        elif event.event_type in ("stage_error", "pipeline_error"):
            await ws.send_json({
                "type": "stage_error",
                "stage": event.stage if event.event_type == "stage_error" else "pipeline",
                "error": event.error,
            })
        elif event.event_type == "pipeline_cancelled":
            await ws.send_json({
                "type": "pipeline_cancelled",
                "error": event.error,
            })
            response_text = "Pipeline was cancelled."
            break
        elif event.event_type == "pipeline_end":
            ctx = event.data["_context"] if event.data else None  # type: ignore[union-attr]
            if ctx and ctx.formatted_response:
                response_text = ctx.formatted_response.get("text", "")
            elif event.data and "metadata" in event.data:
                response_text = str(event.data["metadata"])  # fallback
            break

    if not response_text:
        response_text = "I had an issue processing that request."

    words = response_text.split()
    for i, word in enumerate(words):
        await ws.send_json({
            "type": "stream_token",
            "token": word + " ",
            "complete": i == len(words) - 1,
            "privacy_tier": tier_value,
            "model": model_name,
            "intent": intent,
        })


async def _run_pipeline(request: Request) -> Response:
    """Run the pipeline via streaming and collect the final Response."""
    response_metadata: dict[str, Any] = {}
    response_text = ""
    response_error: str | None = None

    async for event in stream_pipeline(request):
        if event.event_type == "pipeline_end":
            if event.data:
                ctx = event.data.get("_context")
                response_metadata = event.data.get("metadata", {})
                if ctx and hasattr(ctx, "formatted_response") and ctx.formatted_response:
                    response_text = ctx.formatted_response.get("text", "")
        elif event.event_type in ("pipeline_error", "pipeline_cancelled"):
            response_error = event.error
            if event.data:
                response_metadata = event.data.get("metadata", {})

    return Response(
        text=response_text,
        error=response_error,
        metadata=response_metadata,
    )
