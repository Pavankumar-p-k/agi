"""WebSocket adapter — converts WebSocket chat messages to canonical
``Request`` / ``Response`` and delegates to ``process_message()``.

Both ``/ws/chat_stream`` and ``/ws/agent_stream`` call this adapter
instead of duplicating intent classification, LLM calls, and provider
fallback.

**Streaming note:** The pipeline returns a complete ``Response``.  The
adapter splits the response text into word tokens for the WS streaming
protocol, preserving backward compatibility.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

from core.pipeline import process_message
from core.pipeline.messages import Request, Response

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
    """Process a WebSocket chat message through the canonical pipeline.

    Args:
        text: The raw message text.
        user_id: User identifier (usually the session_id).
        session_id: Conversation session identifier.
        context: Optional system context string.
        attachments: Optional list of file/media attachments.
        metadata: Optional extra metadata.

    Returns:
        A dict with at least ``"response"`` (the response text), or
        ``None`` if the pipeline is unavailable.
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

    response: Response = await process_message(request)

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
) -> bool:
    """Process a WS message through the pipeline and stream the result.

    Returns ``True`` if the pipeline handled the request, ``False`` if
    the caller should fall through to legacy handling.

    The response text is split into word tokens and sent as a sequence
    of ``stream_token`` messages matching the existing WS protocol.
    """
    result = await ws_adapter(
        text=text,
        user_id=user_id,
        session_id=session_id,
        context=context,
        metadata=metadata,
    )
    if result is None or result.get("error"):
        return False

    response_text = result.get("response", "")

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

    return True
