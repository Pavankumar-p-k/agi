"""Channel adapter — converts messaging-platform messages to canonical
``Request`` / ``Response`` and delegates to ``process_message()``.

Callers (Telegram, Discord, Slack, Matrix, IRC) all invoke this single
adapter instead of duplicating LLM calls, intent classification, and
provider fallback.
"""
from __future__ import annotations

import logging

from core.pipeline import process_message
from core.pipeline.messages import Request, Response

logger = logging.getLogger(__name__)


async def channel_adapter(
    text: str,
    source: str,
    channel_id: str,
    user_id: str,
    user_name: str,
) -> str:
    """Process a channel message through the canonical pipeline.

    This is a drop-in replacement for the legacy
    ``channels.processor.process_message()``.

    Args:
        text: The raw message text.
        source: Channel identifier (``"discord"``, ``"telegram"``, …).
        channel_id: Platform-specific channel/room identifier.
        user_id: Platform-specific user identifier.
        user_name: Display name of the user.

    Returns:
        The response text to send back to the user.
    """
    request = Request(
        text=text,
        transport=source,
        user_id=user_id,
        session_id=channel_id,
        metadata={
            "channel_id": channel_id,
            "user_name": user_name,
        },
    )
    response: Response = await process_message(request)
    return response.text if not response.error else f"Error: {response.error}"
