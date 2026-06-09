from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx


class JarvisClient:
    """
    Service to communicate with the JARVIS FastAPI backend.
    """
    def __init__(self, base_url: str | None = None):
        if base_url is None:
            base_url = os.environ.get("JARVIS_SERVER", "http://127.0.0.1:8000")
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)

    async def execute_prompt(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Sends a prompt to the /ai_os/execute endpoint."""
        response = await self.client.post("/ai_os/execute", json={
            "prompt": prompt,
            "context": context or {}
        })
        response.raise_for_status()
        return response.json()

    async def stream_events(self) -> AsyncGenerator[dict[str, Any], None]:
        """Streams events from the /ai_os/events SSE endpoint."""
        async with self.client.stream("GET", "/ai_os/events") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[len("data: "):]
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

    async def get_status(self) -> dict[str, Any]:
        """Gets status from /ai_os/status."""
        response = await self.client.get("/ai_os/status")
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
