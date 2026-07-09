"""Internal LLM client for non-pipeline code.

Routes LLM calls through the canonical ``process_message()`` pipeline,
so that every LLM completion flows through the same identity → auth →
execution chain.  Background services, route handlers, and agent code
import this instead of ``core.llm_router`` directly.
"""
from __future__ import annotations

import logging
from typing import Any

from core.pipeline.messages import Request

logger = logging.getLogger(__name__)

_SYSTEM_USER_ID = "__system__"


async def prompt(
    text: str,
    user_id: str = _SYSTEM_USER_ID,
    session_id: str | None = None,
    transport: str = "internal",
    metadata: dict[str, Any] | None = None,
    system: str | None = None,
) -> str:
    """Route *text* through the canonical pipeline and return the output.

    Args:
        text: The prompt / user message.
        user_id:  Defaults to ``__system__`` for background tasks.
        session_id: Optional session identifier.
        transport: Transport label (default ``"internal"``).
        metadata: Extra metadata forwarded to the pipeline context.
        system: Optional system prompt prepended to the text.

    Returns:
        The response text from the pipeline.

    Raises:
        RuntimeError: If the pipeline returns an error.
    """
    from core.pipeline.pipeline import process_message

    full_text = f"{system}\n\n{text}" if system else text
    request = Request(
        text=full_text,
        user_id=user_id,
        session_id=session_id or user_id,
        transport=transport,
        metadata=metadata or {},
    )
    response = await process_message(request)
    if response.error:
        raise RuntimeError(f"Pipeline LLM call failed: {response.error}")
    return response.text
