"""Canonical agent loop and process_message."""
from __future__ import annotations
from typing import AsyncGenerator, Any

_fallback_count = 0


def get_fallback_count() -> int:
    return _fallback_count


async def process_message(message: str, **kwargs) -> Any:
    return {"status": "success", "content": f"Echo: {message}"}


async def stream_agent_loop(message: str, **kwargs) -> AsyncGenerator[str, None]:
    yield f"Processing: {message}"
    yield "Done"
