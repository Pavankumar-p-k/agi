"""REST adapter — converts FastAPI ``ChatRequest`` to canonical
``Request`` / ``Response`` and delegates to ``process_message()``.

The REST endpoint at ``/api/chat`` calls this adapter instead of
duplicating LLM calls, intent classification, and provider fallback.
"""
from __future__ import annotations

import logging

from core.pipeline import process_message
from core.pipeline.messages import Request, Response

logger = logging.getLogger(__name__)


async def rest_adapter(
    message: str,
    user_id: str,
    *,
    session_id: str | None = None,
    context: str | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """Process a REST chat request through the canonical pipeline.

    This is a drop-in replacement for ``routers.chat.chat_handler()``,
    returning the same dict shape so the route handler doesn't need to
    change its persistence logic.

    Args:
        message: The raw message text.
        user_id: Authenticated user identifier.
        session_id: Optional conversation session identifier.
        context: Optional system context string.
        attachments: Optional list of file/media attachments.

    Returns:
        A dict matching the standard API response format (keys: ``response``,
        ``intent``, ``action``, ``model``, ``privacy_tier``, ``epistemic_tags``,
        ``format_used``, ``multi_format``).
    """
    request = Request(
        text=message,
        transport="rest",
        user_id=user_id,
        session_id=session_id or user_id,
        attachments=attachments or [],
        metadata={
            "context": context or "",
        },
    )

    response: Response = await process_message(request)

    if response.error:
        logger.warning("Pipeline returned error for REST request: %s", response.error)
        return {
            "response": response.text or f"Error: {response.error}",
            "intent": {"intent": "chat"},
            "action": {"executed": False},
            "model": "pipeline",
            "privacy_tier": "LOCAL",
            "epistemic_tags": ["ERROR"],
            "format_used": "prose",
            "multi_format": {
                "prose": response.text or response.error,
                "json_data": None,
                "html": None,
                "artifact_type": None,
                "artifact_code": None,
            },
        }

    return {
        "response": response.text,
        "intent": {"intent": "chat"},
        "action": {"executed": True},
        "model": "pipeline",
        "privacy_tier": "LOCAL",
        "epistemic_tags": response.metadata.get("epistemic_tags", ["INFERRED"]),
        "format_used": "prose",
        "multi_format": response.metadata.get(
            "multi_format",
            {
                "prose": response.text,
                "json_data": None,
                "html": None,
                "artifact_type": None,
                "artifact_code": None,
            },
        ),
    }
