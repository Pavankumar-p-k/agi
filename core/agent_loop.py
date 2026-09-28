"""Canonical agent loop and streaming entry points.

All request processing belongs to ``core.pipeline.pipeline.process_message``
(architecture Rule 15). This module only exposes the CLI-facing streaming
helper and a thin echo used by demos.
"""
from __future__ import annotations
from typing import AsyncGenerator, Any

_fallback_count = 0


def get_fallback_count() -> int:
    return _fallback_count


async def run_agent_loop(message: str, **kwargs) -> Any:
    """Echo helper for demos that do not need the full pipeline."""
    return {"status": "success", "content": f"Echo: {message}"}


async def stream_agent_loop(message: str, **kwargs) -> AsyncGenerator[str, None]:
    yield f"Processing: {message}"
    yield "Done"
