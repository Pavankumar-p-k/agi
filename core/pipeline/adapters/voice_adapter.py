"""Voice adapter — converts transcribed speech text to canonical
``Request`` / ``Response`` and delegates to ``process_message()``.

Per the pipeline architecture:

* Speech-specific parts (STT/TTS, audio streaming) stay **outside** the
  pipeline in the voice transport.
* Once speech is converted to text, the transport calls this adapter
  which calls ``process_message()``.
* After the pipeline returns, the transport converts the response back
  to speech via TTS.
"""
from __future__ import annotations

import logging
from typing import Any

from core.pipeline import process_message
from core.pipeline.messages import Request, Response

logger = logging.getLogger(__name__)


async def voice_adapter(
    text: str,
    user_id: str,
    *,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Process transcribed voice text through the canonical pipeline.

    Args:
        text: The transcribed speech text.
        user_id: User identifier.
        session_id: Optional conversation session identifier.
        metadata: Optional extra metadata.

    Returns:
        The response text, or ``None`` if the pipeline is unavailable.
    """
    request = Request(
        text=text,
        transport="voice",
        user_id=user_id,
        session_id=session_id or user_id,
        metadata=metadata or {},
    )

    response: Response = await process_message(request)

    if response.error:
        logger.warning("Pipeline returned error for voice request: %s", response.error)
        return None

    return response.text
